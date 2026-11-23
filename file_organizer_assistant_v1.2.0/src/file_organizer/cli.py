"""
Command-line interface (argparse) for scripting and automation.

    python run_app.py                                   interactive menu
    python run_app.py organize PATH --strategy date --dry-run
    python run_app.py organize PATH --yes --atomic
    python run_app.py undo [--id OP-XXXXXXXX] --yes
    python run_app.py history --keyword report
    python run_app.py stats --report summary.md
    python run_app.py duplicates PATH --yes

Exit codes: 0 success, 1 failure, 2 usage error, 130 interrupted.
"""

import argparse
import logging
from pathlib import Path
from typing import List, Optional

from . import __version__, ui
from .analytics import AnalyticsEngine
from .config import ConfigError, load_category_map
from .core_engine import FileOrganizerEngine
from .logging_setup import setup_logging
from .persistence import PersistenceManager
from .strategies import STRATEGY_NAMES, get_strategy
from .validator import prompt_yes_no, validate_directory
from .workflows import perform_organize, perform_quarantine, perform_undo, plan_duplicates

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="file-organizer", description="File Organizer Assistant")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging to stderr")
    parser.add_argument("--data-dir", default=".", help="folder for history, audit CSV and log file (default: current)")
    sub = parser.add_subparsers(dest="command")

    org = sub.add_parser("organize", help="sort a folder")
    org.add_argument("path")
    org.add_argument("--strategy", choices=STRATEGY_NAMES, default="type")
    org.add_argument("--config", help="JSON file with custom {category: [extensions]} rules")
    org.add_argument("--dry-run", action="store_true", help="simulate only; modify nothing")
    org.add_argument("--atomic", action="store_true", help="revert everything if any move fails")
    org.add_argument("--recursive", action="store_true", help="also organize files inside sub-folders")
    org.add_argument("--include-hidden", action="store_true", help="also organize dot-files")
    org.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")

    undo = sub.add_parser("undo", help="roll back an operation (default: the latest)")
    undo.add_argument("--id", dest="operation_id")
    undo.add_argument("-y", "--yes", action="store_true")

    hist = sub.add_parser("history", help="search past records")
    hist.add_argument("--keyword", default="")
    hist.add_argument("--category", default="")
    hist.add_argument("--limit", type=int, default=20)

    stats = sub.add_parser("stats", help="show metrics and export the Markdown report")
    stats.add_argument("--report", default="organizer_executive_summary.md")

    web = sub.add_parser("web", help="start the browser interface (http://127.0.0.1:5000)")
    web.add_argument("--port", type=int, default=5000)
    web.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")

    dup = sub.add_parser("duplicates", help="find byte-identical files and quarantine the extra copies")
    dup.add_argument("path")
    dup.add_argument("--no-recursive", action="store_true")
    dup.add_argument("--dry-run", action="store_true")
    dup.add_argument("--atomic", action="store_true")
    dup.add_argument("-y", "--yes", action="store_true")
    return parser


def _persistence(data_dir: str) -> PersistenceManager:
    base = Path(data_dir).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    return PersistenceManager(base / "organizer_history.json", base / "organizer_audit.csv")


def _confirm(args: argparse.Namespace, question: str) -> bool:
    return bool(args.yes) or prompt_yes_no(question)


def _cmd_organize(args: argparse.Namespace, persistence: PersistenceManager) -> int:
    target = str(validate_directory(args.path))
    category_map = load_category_map(args.config) if args.config else None
    engine = FileOrganizerEngine(category_map, get_strategy(args.strategy, category_map), include_hidden=args.include_hidden,
                                 exclude_paths=persistence.state_files())

    if engine.has_pending_journal(target):
        ui.warning("[Recovery] An interrupted run was detected in this folder.")
        if _confirm(args, "Restore the partially moved files first? (y/n): "):
            ui.show_rollback_result(*engine.recover_pending(target))

    plan_summary = engine.summarize_plan(engine.iter_scan(target, args.recursive))
    if plan_summary["total_files"] == 0:
        ui.warning("[Notice] No organize-able files detected in target folder.")
        return 0
    ui.show_preview(plan_summary)

    if args.dry_run:
        ui.show_dry_run_result(engine.execute_organization(target, engine.iter_scan(target, args.recursive), dry_run=True))
        ui.info("[Dry run] No files were modified.")
        return 0
    if not _confirm(args, "Execute file relocations now? (y/n): "):
        ui.warning("[Cancelled] No files were modified.")
        return 0

    summary = perform_organize(engine, persistence, target, atomic=args.atomic, recursive=args.recursive)
    ui.show_operation_result(summary)
    return 1 if summary["failed_moves"] else 0


def _cmd_undo(args: argparse.Namespace, persistence: PersistenceManager) -> int:
    if args.operation_id:
        operation = persistence.find_operation(args.operation_id)
        if operation is None or operation.get("rolled_back"):
            ui.error(f"[Error] Operation '{args.operation_id}' not found or already rolled back.")
            return 1
    else:
        candidates = persistence.get_rollbackable(1)
        if not candidates:
            ui.warning("[Info] No recorded operations found to rollback.")
            return 0
        operation = candidates[0]
    if not _confirm(args, f"Restore files of {operation.get('operation_id')}? (y/n): "):
        ui.warning("[Cancelled] Nothing was changed.")
        return 0
    restored, failed, errors = perform_undo(FileOrganizerEngine(exclude_paths=persistence.state_files()), persistence, operation)
    ui.show_rollback_result(restored, failed, errors)
    return 1 if failed else 0


def _cmd_history(args: argparse.Namespace, persistence: PersistenceManager) -> int:
    results = AnalyticsEngine(persistence.load_history()).search_records(args.keyword, args.category)
    ui.success(f"Found {len(results)} matching records:")
    for record in results[: max(args.limit, 0)]:
        ui.plain(f"{str(record.get('filename'))[:40]:<42} {str(record.get('category')):<18} "
                 f"{str(record.get('timestamp'))[:19]}  {record.get('operation_id')}")
    return 0


def _cmd_stats(args: argparse.Namespace, persistence: PersistenceManager) -> int:
    analytics = AnalyticsEngine(persistence.load_history())
    metrics = analytics.compute_metrics()
    ui.heading("=== PERFORMANCE METRICS ===")
    ui.plain(f" Total Operations:      {metrics['total_operations']}")
    ui.plain(f" Total Files Organized: {metrics['total_files_organized']}")
    ui.plain(f" Total Data Volume:     {metrics['total_volume_mb']} MB")
    ui.plain(f" Avg Files / Operation: {metrics['avg_files_per_operation']}")
    ui.success(f"Report written to '{analytics.export_markdown_report(args.report)}'")
    return 0


def _cmd_duplicates(args: argparse.Namespace, persistence: PersistenceManager) -> int:
    root = str(validate_directory(args.path))
    groups, plan = plan_duplicates(root, recursive=not args.no_recursive, exclude=persistence.state_files())
    if not groups:
        ui.success("[Info] No duplicate files found.")
        return 0
    ui.warning(f"Found {len(groups)} duplicate group(s); {len(plan)} redundant copies:")
    for group in groups:
        ui.plain(f"  KEEP  {group[0]}")
        for duplicate in group[1:]:
            ui.plain(f"  MOVE  {duplicate}")
    engine = FileOrganizerEngine(exclude_paths=persistence.state_files())
    if args.dry_run:
        ui.show_dry_run_result(engine.execute_organization(root, plan, dry_run=True))
        return 0
    if not _confirm(args, "Move redundant copies into 'Duplicates'? (y/n): "):
        ui.warning("[Cancelled] No files were modified.")
        return 0
    summary = perform_quarantine(engine, persistence, root, plan, atomic=args.atomic)
    ui.show_operation_result(summary)
    return 1 if summary["failed_moves"] else 0


def _cmd_web(args: argparse.Namespace, persistence: PersistenceManager) -> int:
    from .web import serve  # local import: the web stack is only loaded when needed

    return serve(persistence, port=args.port, open_browser=not args.no_browser)


_COMMANDS = {
    "web": _cmd_web,
    "organize": _cmd_organize,
    "undo": _cmd_undo,
    "history": _cmd_history,
    "stats": _cmd_stats,
    "duplicates": _cmd_duplicates,
}


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point. Without a sub-command the interactive menu is started."""
    args = build_parser().parse_args(argv)
    data_dir = Path(args.data_dir).expanduser()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        ui.error(f"[Error] Cannot use data directory '{data_dir}': {exc}")
        return 1
    setup_logging(verbose=args.verbose, log_file=data_dir / "organizer.log")

    if args.command is None:
        from .main import main as interactive_main  # local import: avoids a cycle and keeps CLI start-up light

        interactive_main(_persistence(args.data_dir))
        return 0

    try:
        return _COMMANDS[args.command](args, _persistence(args.data_dir))
    except (ValueError, ConfigError) as exc:  # validation problems: bad path, bad config file
        ui.error(f"[Error] {exc}")
        return 1
    except OSError as exc:
        logger.exception("Command '%s' failed", args.command)
        ui.error(f"[Error] File system problem: {exc}")
        return 1
    except (KeyboardInterrupt, EOFError):
        ui.warning("\n[Cancelled] Interrupted by user.")
        return 130
