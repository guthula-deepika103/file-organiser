"""
Data persistence layer for File Organizer Assistant.

* JSON history is written atomically (temp file + fsync + ``os.replace``), so a
  crash can never leave a half-written history file.
* A CSV audit log is appended per file (with spreadsheet-formula neutralisation).
* Corrupted JSON is detected, backed up and replaced by a clean store.
"""

import csv
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .config import DEFAULT_CSV_AUDIT_LOG, DEFAULT_JSON_PERSISTENCE, DEFAULT_LOG_FILE
from .models import STATUS_ROLLED_BACK, STATUS_SUCCESS

logger = logging.getLogger(__name__)

PathLike = Union[str, "os.PathLike[str]"]
_CSV_HEADER = [
    "operation_id", "timestamp", "filename", "source_dir",
    "target_dir", "category", "file_size_bytes", "status",
]
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: Any) -> Any:
    """Prefixes cells that spreadsheets would execute as formulas (CSV injection)."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


class PersistenceManager:
    def __init__(self, json_file: PathLike = DEFAULT_JSON_PERSISTENCE, csv_file: PathLike = DEFAULT_CSV_AUDIT_LOG):
        self.json_file = Path(json_file)
        self.csv_file = Path(csv_file)
        self._ensure_storage_initialized()

    # --------------------------------------------------------------- set-up
    def _ensure_storage_initialized(self) -> None:
        """Creates missing stores and recovers from a corrupted history file."""
        if not self.json_file.exists():
            self.save_history([])
        else:
            try:
                with self.json_file.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
                    raise ValueError("Root JSON payload must be a list of operation objects.")
            except (json.JSONDecodeError, ValueError, UnicodeDecodeError, OSError) as err:
                logger.warning("History '%s' corrupted or unreadable (%s); re-initialising.", self.json_file, err)
                backup = self.json_file.with_name(self.json_file.name + ".corrupted.bak")
                try:
                    os.replace(self.json_file, backup)
                    logger.info("Corrupted history backed up to '%s'.", backup)
                except OSError as exc:
                    logger.error("Could not back up corrupted history: %s", exc)
                self.save_history([])

        try:
            if not self.csv_file.exists() or self.csv_file.stat().st_size == 0:
                self._initialize_csv_header()
        except OSError as exc:
            logger.error("Cannot access CSV audit log '%s': %s", self.csv_file, exc)

    def _initialize_csv_header(self) -> None:
        try:
            with self.csv_file.open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle).writerow(_CSV_HEADER)
        except OSError as exc:
            logger.error("Failed to initialise CSV header: %s", exc)

    def state_files(self) -> List[Path]:
        """Files owned by the application itself (history, audit, log); organizers must skip them."""
        folder = self.json_file.parent
        files = [self.json_file, self.csv_file, self.json_file.with_name(self.json_file.name + ".corrupted.bak")]
        files.append(folder / DEFAULT_LOG_FILE)
        files.extend(folder / f"{DEFAULT_LOG_FILE}.{n}" for n in range(1, 4))
        return files

    # ----------------------------------------------------------------- JSON
    def load_history(self) -> List[Dict[str, Any]]:
        """Reads the complete operation history (empty list when unreadable)."""
        try:
            with self.json_file.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.error("Could not read history '%s': %s", self.json_file, exc)
            return []
        return data if isinstance(data, list) else []

    def save_history(self, history_data: List[Dict[str, Any]]) -> bool:
        """Atomically serialises the history: a crash leaves either the old or the new file."""
        tmp_name: Optional[str] = None
        try:
            self.json_file.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(dir=str(self.json_file.parent), prefix=self.json_file.name, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(history_data, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.json_file)
            return True
        except (OSError, TypeError, ValueError) as exc:
            logger.error("Failed saving history to JSON: %s", exc)
            if tmp_name:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
            return False

    # ------------------------------------------------------------ operations
    def log_operation(self, operation_record: Dict[str, Any]) -> bool:
        """Appends a completed batch to the JSON history and the CSV audit log."""
        if operation_record.get("dry_run"):
            logger.debug("Dry-run %s not persisted.", operation_record.get("operation_id"))
            return False

        history = self.load_history()
        history.append(operation_record)
        json_ok = self.save_history(history)

        op_id = operation_record.get("operation_id", "N/A")
        ts = operation_record.get("timestamp", datetime.now().isoformat())
        csv_ok = self._append_csv_rows(
            (op_id, ts, entry) for entry in operation_record.get("moved_files", [])
        )
        return json_ok and csv_ok

    def _append_csv_rows(self, rows) -> bool:
        try:
            with self.csv_file.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                for op_id, ts, entry in rows:
                    writer.writerow([_csv_safe(v) for v in (
                        op_id, ts, entry.get("filename"), entry.get("source_dir"),
                        entry.get("target_dir"), entry.get("category"),
                        entry.get("size_bytes", 0), entry.get("status", STATUS_SUCCESS),
                    )])
            return True
        except OSError as exc:
            logger.error("Failed appending to CSV audit log: %s", exc)
            return False

    def update_operation(self, operation_record: Dict[str, Any]) -> bool:
        """Replaces the stored copy of an operation (used after a rollback)."""
        op_id = operation_record.get("operation_id")
        history = self.load_history()
        for index, stored in enumerate(history):
            if stored.get("operation_id") == op_id:
                history[index] = operation_record
                return self.save_history(history)
        logger.warning("Operation %s not found in history; nothing updated.", op_id)
        return False

    def log_rollback(self, operation_record: Dict[str, Any], restored: List[Dict[str, Any]]) -> bool:
        """Adds ROLLED_BACK rows to the CSV audit trail."""
        now = datetime.now().isoformat()
        op_id = operation_record.get("operation_id", "N/A")
        rows = ((op_id, now, dict(entry, status=STATUS_ROLLED_BACK)) for entry in restored)
        return self._append_csv_rows(rows)

    def get_rollbackable(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Most recent operations that still have files that can be restored (newest first)."""
        candidates = [
            op for op in self.load_history()
            if not op.get("rolled_back")
            and any(r.get("status") == STATUS_SUCCESS for r in op.get("moved_files", []))
        ]
        return list(reversed(candidates[-limit:]))

    def find_operation(self, operation_id: str) -> Optional[Dict[str, Any]]:
        wanted = operation_id.strip().upper()
        for op in self.load_history():
            if str(op.get("operation_id", "")).upper() == wanted:
                return op
        return None
