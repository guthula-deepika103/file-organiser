"""
Application workflows shared by the interactive menu and the CLI.

They combine the engine and the persistence layer but never prompt or print,
which keeps the two front-ends thin and the behaviour identical.
"""

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .config import DEMO_MARKER_FILENAME
from .core_engine import FileOrganizerEngine
from .duplicates import build_duplicate_plan, find_duplicate_groups
from .models import STATUS_ROLLED_BACK, STATUS_SUCCESS
from .persistence import PersistenceManager

logger = logging.getLogger(__name__)

DEMO_FILES = [
    "Hackathon_Pitch_Deck.pptx", "Q3_Financial_Model.xlsx", "Project_Brief_105.pdf",
    "Community_Survey_Data.csv", "App_Architecture_Diagram.png", "User_Interface_Mockup.jpg",
    "Backend_API_Server.py", "Database_Schema.sql", "Deployment_Script.sh",
    "System_Logs_2026.txt", "System_Logs_2026_backup.txt",  # identical content -> duplicate demo
    "Archive_Source_Backup.zip", "Promo_Video_Teaser.mp4",
]


def perform_organize(
    engine: FileOrganizerEngine,
    persistence: PersistenceManager,
    target_dir: str,
    atomic: bool = False,
    recursive: bool = False,
) -> Dict[str, Any]:
    """Streams the scan straight into the executor and records the result in the history."""
    plan = engine.iter_scan(target_dir, recursive)
    if recursive:
        plan = iter(list(plan))  # freeze the plan: files are moved while sub-folders are being walked
    summary = engine.execute_organization(target_dir, plan, atomic=atomic)
    if summary["total_files_processed"] > 0:
        persistence.log_operation(summary)
    return summary


def plan_duplicates(
    root: str, recursive: bool = True, exclude: Optional[Iterable[Path]] = None
) -> Tuple[List[List[Path]], List[Dict[str, Any]]]:
    """Returns (duplicate groups, plan that would quarantine the redundant copies)."""
    groups = find_duplicate_groups(Path(root), recursive=recursive, exclude=exclude)
    return groups, list(build_duplicate_plan(groups, Path(root)))


def perform_quarantine(
    engine: FileOrganizerEngine,
    persistence: PersistenceManager,
    root: str,
    plan: List[Dict[str, Any]],
    atomic: bool = False,
) -> Dict[str, Any]:
    summary = engine.execute_organization(root, plan, atomic=atomic)
    if summary["total_files_processed"] > 0:
        persistence.log_operation(summary)
    return summary


def perform_undo(
    engine: FileOrganizerEngine,
    persistence: PersistenceManager,
    operation: Dict[str, Any],
) -> Tuple[int, int, List[str]]:
    """Rolls an operation back and persists the new state + audit rows."""
    outstanding = [r for r in operation.get("moved_files", []) if r.get("status") == STATUS_SUCCESS]
    restored_count, failed_count, errors = engine.rollback_operation(operation)
    restored = [r for r in outstanding if r.get("status") == STATUS_ROLLED_BACK]
    if restored:
        persistence.update_operation(operation)
        persistence.log_rollback(operation, restored)
    return restored_count, failed_count, errors


def seed_demo_workspace(demo_dir: str = "demo_unorganized_workspace") -> str:
    """
    (Re)creates a sample folder for live demonstrations.
    An existing folder is only wiped when it carries the demo marker file, so a
    user's real folder with the same name is never deleted.
    """
    demo_path = Path(demo_dir).expanduser().resolve()
    marker = demo_path / DEMO_MARKER_FILENAME
    if demo_path.exists() and marker.exists():
        shutil.rmtree(demo_path)
    demo_path.mkdir(parents=True, exist_ok=True)
    marker.write_text("Created by File Organizer Assistant demo mode.\n", encoding="utf-8")

    for name in DEMO_FILES:
        base_name = name.replace("_backup", "")
        (demo_path / name).write_text(
            f"Sample data content for {base_name} in hackathon demo workspace.\n", encoding="utf-8"
        )
    return str(demo_path)
