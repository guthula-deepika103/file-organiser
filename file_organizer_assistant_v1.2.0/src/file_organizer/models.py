"""
Shared data shapes and status constants.

Plans and history records stay plain dictionaries (JSON friendly, backward
compatible with v1.0 history files); the TypedDicts below document their shape.
"""

from typing import List

try:  # Python 3.8+
    from typing import TypedDict
except ImportError:  # pragma: no cover
    from typing_extensions import TypedDict  # type: ignore

STATUS_SUCCESS = "SUCCESS"
STATUS_PLANNED = "PLANNED"
STATUS_ROLLED_BACK = "ROLLED_BACK"
STATUS_FAILED = "FAILED"  # real values look like "FAILED: <reason>"


class PlannedMove(TypedDict):
    """One entry of an organisation plan (output of the scanner)."""

    filename: str
    extension: str
    category: str
    source_path: str
    target_folder: str
    target_path: str
    size_bytes: int


class MoveRecord(TypedDict, total=False):
    """One executed (or simulated) move, stored in the operation history."""

    filename: str
    source_path: str
    target_path: str
    source_dir: str
    target_dir: str
    category: str
    size_bytes: int
    status: str
    rolled_back_at: str


class OperationSummary(TypedDict, total=False):
    """Result of ``FileOrganizerEngine.execute_organization``."""

    operation_id: str
    timestamp: str
    target_directory: str
    strategy: str
    dry_run: bool
    atomic: bool
    aborted: bool
    rolled_back: bool
    total_files_processed: int
    successful_moves: int
    planned_moves: int
    failed_moves: int
    errors: List[str]
    moved_files: List[MoveRecord]


def is_failed(status: object) -> bool:
    return isinstance(status, str) and status.startswith(STATUS_FAILED)
