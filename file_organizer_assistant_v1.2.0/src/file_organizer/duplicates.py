"""
Duplicate-file detection.

Files are first bucketed by size (cheap) and only same-size candidates are
hashed with SHA-256 in fixed-size chunks, so large files never load fully into
memory. The oldest copy of each group is kept in place; the others become a
normal organisation plan (moved into ``Duplicates/``), which means they get the
same preview, journaling, history and rollback guarantees as any other batch.
"""

import hashlib
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set

from .config import DUPLICATES_CATEGORY
from .pathutils import normalize

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024


def iter_files(root: Path, recursive: bool = True, exclude: Optional[Set[str]] = None) -> Iterator[Path]:
    """Lazily yields regular files below ``root`` (skips symlinks, hidden entries and ``Duplicates/``)."""
    stack = [Path(root)]
    while stack:
        current = stack.pop()
        try:
            iterator = os.scandir(current)
        except OSError as exc:
            logger.warning("Cannot scan '%s': %s", current, exc)
            continue
        with iterator:
            for entry in iterator:
                try:
                    if entry.is_symlink() or entry.name.startswith("."):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if recursive and entry.name != DUPLICATES_CATEGORY:
                            stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        if exclude and str(normalize(entry.path)) in exclude:
                            continue
                        yield Path(entry.path)
                except OSError as exc:
                    logger.warning("Skipping '%s': %s", entry.path, exc)


def file_digest(path: Path) -> str:
    """SHA-256 of a file, read in 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _keep_order(path: Path):
    """Oldest file first (it is the one that stays), name as tie-breaker."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = float("inf")
    return (mtime, str(path))


def find_duplicate_groups(
    root: Path, recursive: bool = True, min_size: int = 1, exclude: Optional[Iterable[Path]] = None
) -> List[List[Path]]:
    """
    Returns groups of byte-identical files. Within each group the first path is
    the one to keep. Empty files are ignored by default (``min_size=1``).
    """
    excluded = {str(normalize(p)) for p in exclude} if exclude else None
    by_size: Dict[int, List[Path]] = defaultdict(list)
    for path in iter_files(root, recursive, excluded):
        try:
            size = path.stat().st_size
        except OSError as exc:
            logger.warning("Cannot stat '%s': %s", path, exc)
            continue
        if size >= min_size:
            by_size[size].append(path)

    groups: List[List[Path]] = []
    for paths in by_size.values():
        if len(paths) < 2:
            continue
        by_hash: Dict[str, List[Path]] = defaultdict(list)
        for path in paths:
            try:
                by_hash[file_digest(path)].append(path)
            except OSError as exc:
                logger.warning("Cannot hash '%s': %s", path, exc)
        groups.extend(sorted(group, key=_keep_order) for group in by_hash.values() if len(group) > 1)

    groups.sort(key=lambda group: str(group[0]))
    logger.info("Duplicate scan of '%s' found %d group(s).", root, len(groups))
    return groups


def build_duplicate_plan(groups: List[List[Path]], root: Path) -> Iterator[Dict[str, Any]]:
    """Turns duplicate groups into engine plan entries (everything but the kept copy)."""
    folder = Path(root) / DUPLICATES_CATEGORY
    for group in groups:
        for duplicate in group[1:]:
            try:
                size = duplicate.stat().st_size
            except OSError:
                size = 0
            extension = os.path.splitext(duplicate.name)[1]
            yield {
                "filename": duplicate.name,
                "extension": extension if extension else "[No Ext]",
                "category": DUPLICATES_CATEGORY,
                "source_path": str(duplicate),
                "target_folder": str(folder),
                "target_path": str(folder / duplicate.name),
                "size_bytes": size,
            }


def wasted_bytes(groups: List[List[Path]]) -> int:
    """Disk space occupied by the redundant copies."""
    total = 0
    for group in groups:
        for duplicate in group[1:]:
            try:
                total += duplicate.stat().st_size
            except OSError:
                continue
    return total
