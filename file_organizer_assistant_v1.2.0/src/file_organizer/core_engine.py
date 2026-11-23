"""
Core business logic engine for File Organizer Assistant.

Responsibilities (and nothing else - no terminal output lives here):
  * lazy, generator-based directory scanning
  * plan summarisation (O(1) memory)
  * engine-level dry-run, optional all-or-nothing (atomic) execution
  * write-ahead journalling + crash recovery
  * safe rollback / undo
"""

import logging
import os
import shutil
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple, Union

from .config import DEFAULT_CATEGORY_MAP, DUPLICATES_CATEGORY, JOURNAL_FILENAME, validate_category_map
from .models import STATUS_FAILED, STATUS_PLANNED, STATUS_ROLLED_BACK, STATUS_SUCCESS, is_failed
from .pathutils import is_within, normalize, prune_empty_dirs, unique_destination
from .strategies import CategorizationStrategy, ExtensionStrategy
from .transaction import MoveJournal

logger = logging.getLogger(__name__)

_MOVE_ERRORS = (OSError, shutil.Error)


class FileOrganizerEngine:
    def __init__(
        self,
        custom_category_map: Optional[Dict[str, List[str]]] = None,
        strategy: Optional[CategorizationStrategy] = None,
        include_hidden: bool = False,
        exclude_paths: Optional[Iterable[Union[str, "os.PathLike[str]"]]] = None,
    ):
        self.category_map = validate_category_map(custom_category_map) if custom_category_map else DEFAULT_CATEGORY_MAP
        self._extension_strategy = ExtensionStrategy(self.category_map)
        self.strategy: CategorizationStrategy = strategy or self._extension_strategy
        self.include_hidden = include_hidden
        # The app's own state files (history, audit log, log file) must never be organized.
        self._excluded: Set[str] = {str(normalize(p)) for p in (exclude_paths or [])}

    # ---------------------------------------------------------------- lookup
    def get_category_for_extension(self, ext: str) -> str:
        """Determines the mapped category folder name for a given extension."""
        return self._extension_strategy.category_for_extension(ext)

    # -------------------------------------------------------------- scanning
    def iter_scan(self, target_dir: str, recursive: bool = False) -> Iterator[Dict[str, Any]]:
        """
        Lazily yields one plan entry per regular file (generator).

        Memory use is constant regardless of directory size, so folders with
        hundreds of thousands of files can be scanned and previewed without
        loading them all at once. Symlinks and (by default) hidden files are
        skipped. With ``recursive=True`` sub-folders are walked too (hidden
        folders, symlinked folders and ``Duplicates/`` are skipped, and files
        already sitting in their destination folder are left alone, so running
        the organizer twice is harmless).
        """
        root = Path(target_dir)
        if not root.is_dir():
            logger.warning("Scan skipped: '%s' is not an existing directory.", root)
            return
        pending_dirs = [root]
        while pending_dirs:
            current = pending_dirs.pop()
            try:
                iterator = os.scandir(current)
            except OSError as exc:
                logger.error("Cannot scan '%s': %s", current, exc)
                continue
            with iterator:
                for entry in iterator:
                    if recursive and self._is_walkable_dir(entry):
                        pending_dirs.append(Path(entry.path))
                        continue
                    plan_entry = self._plan_entry(root, entry)
                    if plan_entry is not None:
                        yield plan_entry

    @staticmethod
    def _is_walkable_dir(entry: "os.DirEntry[str]") -> bool:
        try:
            return (
                entry.is_dir(follow_symlinks=False)
                and not entry.name.startswith(".")
                and entry.name != DUPLICATES_CATEGORY
            )
        except OSError:
            return False

    def _plan_entry(self, root: Path, entry: "os.DirEntry[str]") -> Optional[Dict[str, Any]]:
        name = entry.name
        if name == JOURNAL_FILENAME or (name.startswith(".") and not self.include_hidden):
            return None
        if self._excluded and str(normalize(entry.path)) in self._excluded:
            return None
        try:
            if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                return None
            stat_result = entry.stat(follow_symlinks=False)
        except OSError as exc:
            logger.warning("Skipping unreadable entry '%s': %s", name, exc)
            return None

        source = Path(entry.path)
        category = self.strategy.categorize(source, stat_result)
        extension = os.path.splitext(name)[1]
        folder = root / category
        if source.parent == folder:
            return None  # already where it belongs
        return {
            "filename": name,
            "extension": extension if extension else "[No Ext]",
            "category": category,
            "source_path": str(source),
            "target_folder": str(folder),
            "target_path": str(folder / name),
            "size_bytes": stat_result.st_size,
        }

    def scan_directory(self, target_dir: str) -> List[Dict[str, Any]]:
        """Convenience wrapper: materialises ``iter_scan`` as a name-sorted list."""
        return sorted(self.iter_scan(target_dir), key=lambda item: item["filename"])

    @staticmethod
    def summarize_plan(plan: Iterable[Dict[str, Any]], sample_size: int = 25) -> Dict[str, Any]:
        """Single streaming pass producing totals, per-category counts and a small sample."""
        total_files = 0
        total_bytes = 0
        by_category: Counter = Counter()
        sample: List[Dict[str, Any]] = []
        for item in plan:
            total_files += 1
            total_bytes += item.get("size_bytes", 0)
            by_category[item["category"]] += 1
            if len(sample) < sample_size:
                sample.append(item)
        return {
            "total_files": total_files,
            "total_bytes": total_bytes,
            "by_category": dict(by_category),
            "sample": sample,
        }

    # ------------------------------------------------------------- execution
    def execute_organization(
        self,
        target_dir: str,
        file_plan: Iterable[Dict[str, Any]],
        dry_run: bool = False,
        atomic: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes (or, with ``dry_run=True``, only simulates) the relocation plan.

        dry_run  - engine-level preview: nothing is created, moved or journaled;
                   records carry status PLANNED and the collision-resolved
                   destination paths.
        atomic   - all-or-nothing: the first failure reverts every move made so
                   far in this batch.
        Ctrl+C during a real run also reverts the batch before re-raising, and a
        write-ahead journal allows ``recover_pending`` after a hard crash.

        ``file_plan`` may be any iterable, including the ``iter_scan`` generator.
        """
        operation_id = f"OP-{uuid.uuid4().hex[:8].upper()}"
        timestamp = datetime.now().isoformat()
        root = Path(target_dir)
        journal = None if dry_run else MoveJournal(root)

        records: List[Dict[str, Any]] = []
        errors: List[str] = []
        completed: List[Tuple[Path, Path]] = []
        reserved: Set[str] = set()
        total = 0
        aborted = False
        revert_failures = 0

        try:
            for item in file_plan:
                total += 1
                record = self._new_record(item, root)
                source = Path(item["source_path"])
                folder = Path(item["target_folder"])
                try:
                    destination = unique_destination(folder, item["filename"], reserved if dry_run else None)
                    record["target_path"] = str(destination)
                    if dry_run:
                        reserved.add(str(destination))
                        record["status"] = STATUS_PLANNED
                        records.append(record)
                        continue
                    folder.mkdir(parents=True, exist_ok=True)
                    journal.record(source, destination)  # write-ahead: intent first, then move
                    shutil.move(str(source), str(destination))
                except _MOVE_ERRORS as exc:
                    message = f"Failed to move '{item['filename']}': {exc}"
                    logger.error(message)
                    errors.append(message)
                    record["status"] = f"{STATUS_FAILED}: {exc}"
                    records.append(record)
                    if atomic:
                        aborted = True
                        break
                    continue
                record["status"] = STATUS_SUCCESS
                records.append(record)
                completed.append((source, destination))

            if aborted and completed:
                logger.warning("Atomic batch aborted; reverting %d completed move(s).", len(completed))
                revert_failures = self._revert_moves(completed, root)
                for record in records:
                    if record["status"] == STATUS_SUCCESS:
                        record["status"] = f"{STATUS_FAILED}: reverted (atomic batch aborted)"
        except KeyboardInterrupt:
            logger.warning("Interrupted by user; reverting %d completed move(s).", len(completed))
            if self._revert_moves(completed, root) == 0 and journal is not None:
                journal.commit()
            raise
        else:
            if journal is not None:
                if revert_failures == 0:
                    journal.commit()
                else:
                    journal.close()  # keep journal so recover_pending can finish the job
        finally:
            if journal is not None:
                journal.close()

        successes = sum(1 for r in records if r["status"] == STATUS_SUCCESS)
        planned = sum(1 for r in records if r["status"] == STATUS_PLANNED)
        failed = sum(1 for r in records if is_failed(r["status"]))
        logger.info(
            "%s %s: %d processed, %d succeeded, %d failed.",
            "Dry-run" if dry_run else "Operation", operation_id, total, successes, failed,
        )
        return {
            "operation_id": operation_id,
            "timestamp": timestamp,
            "target_directory": str(root),
            "strategy": self.strategy.name,
            "dry_run": dry_run,
            "atomic": atomic,
            "aborted": aborted,
            "rolled_back": False,
            "total_files_processed": total,
            "successful_moves": successes,
            "planned_moves": planned,
            "failed_moves": failed,
            "errors": errors,
            "moved_files": records,
        }

    @staticmethod
    def _new_record(item: Dict[str, Any], root: Path) -> Dict[str, Any]:
        return {
            "filename": item["filename"],
            "source_path": item["source_path"],
            "target_path": item["target_path"],
            "source_dir": str(root),
            "target_dir": item["target_folder"],
            "category": item["category"],
            "size_bytes": item.get("size_bytes", 0),
            "status": STATUS_PLANNED,
        }

    # -------------------------------------------------------------- restore
    @staticmethod
    def _restore_file(current: Path, original: Path) -> Path:
        """
        Moves ``current`` back to ``original``. If something new now occupies
        the original name it is never overwritten - the restored file gets a
        ``_restoredN`` suffix instead.
        """
        original.parent.mkdir(parents=True, exist_ok=True)
        destination = original
        if destination.exists():
            destination = unique_destination(original.parent, original.name, tag="restored")
            logger.warning("'%s' already exists; restoring as '%s'.", original, destination.name)
        shutil.move(str(current), str(destination))
        return destination

    def _revert_moves(self, completed: List[Tuple[Path, Path]], boundary: Path) -> int:
        """Reverses (src -> dst) moves newest-first. Returns the number of failures."""
        failures = 0
        for source, destination in reversed(completed):
            try:
                self._restore_file(destination, source)
                prune_empty_dirs(destination.parent, boundary)
            except _MOVE_ERRORS as exc:
                failures += 1
                logger.error("Could not revert '%s': %s", destination, exc)
        return failures

    def rollback_operation(self, operation_record: Dict[str, Any]) -> Tuple[int, int, List[str]]:
        """
        Reverses a logged batch by returning moved files to their original paths.

        Files that were restored get ``status = ROLLED_BACK`` (the record is
        updated in place so callers can persist it); a second call therefore only
        retries what is still outstanding. Paths outside the operation's folder
        are refused, so a tampered history file cannot move arbitrary files.

        Returns (success_count, fail_count, error_messages).
        """
        success_count = 0
        errors: List[str] = []
        base = operation_record.get("target_directory")
        records = operation_record.get("moved_files", [])

        for record in reversed(records):
            if record.get("status") != STATUS_SUCCESS:
                continue
            current = record.get("target_path")
            original = record.get("source_path")
            name = record.get("filename")
            if not current or not original:
                errors.append(f"Incomplete record for '{name}'.")
                continue
            if base and not (is_within(current, base) and is_within(original, base)):
                message = f"Refusing to rollback '{name}': path outside '{base}'."
                logger.error(message)
                errors.append(message)
                continue
            if not Path(current).exists():
                errors.append(f"File '{current}' missing during rollback.")
                continue
            try:
                self._restore_file(Path(current), Path(original))
            except _MOVE_ERRORS as exc:
                logger.error("Rollback of '%s' failed: %s", name, exc)
                errors.append(f"Could not rollback '{name}': {exc}")
                continue
            record["status"] = STATUS_ROLLED_BACK
            record["rolled_back_at"] = datetime.now().isoformat()
            success_count += 1
            if base:
                prune_empty_dirs(Path(current).parent, Path(base))

        if not any(r.get("status") == STATUS_SUCCESS for r in records):
            operation_record["rolled_back"] = True
        return success_count, len(errors), errors

    # ------------------------------------------------------ crash recovery
    @staticmethod
    def has_pending_journal(target_dir: str) -> bool:
        """True when a previous run in ``target_dir`` was interrupted mid-batch."""
        return MoveJournal(target_dir).has_pending()

    def recover_pending(self, target_dir: str) -> Tuple[int, int, List[str]]:
        """Reverts the moves of an interrupted batch using its journal."""
        root = normalize(target_dir)
        journal = MoveJournal(root)
        restored = 0
        errors: List[str] = []
        for source, destination in reversed(journal.read_entries()):
            if not (is_within(source, root) and is_within(destination, root)):
                errors.append(f"Journal entry outside '{root}' ignored: {destination}")
                continue
            if not destination.exists():
                # The move never happened (crash between journal write and move) but the
                # category folder may already have been created - tidy it up.
                prune_empty_dirs(destination.parent, root)
                continue
            try:
                self._restore_file(destination, source)
                prune_empty_dirs(destination.parent, root)
                restored += 1
            except _MOVE_ERRORS as exc:
                logger.error("Recovery failed for '%s': %s", destination, exc)
                errors.append(f"Could not recover '{destination.name}': {exc}")
        if not errors:
            journal.commit()
        return restored, len(errors), errors
