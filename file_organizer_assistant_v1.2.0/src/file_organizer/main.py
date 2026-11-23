"""
Interactive console application for File Organizer Assistant (Project #105).

Thin presentation layer: it asks questions (validator), shows results (ui) and
delegates all work to the engine / workflows. Each menu entry is a small
handler function registered in ``MENU`` instead of one long if/elif chain.
"""

import logging
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from . import ui
from .analytics import AnalyticsEngine
from .core_engine import FileOrganizerEngine
from .logging_setup import setup_logging
from .persistence import PersistenceManager
from .strategies import STRATEGY_NAMES, get_strategy
from .validator import (
    prompt_choice,
    prompt_existing_directory,
    prompt_menu_choice,
    prompt_text,
    prompt_yes_no,
)
from .workflows import (
    perform_organize,
    perform_quarantine,
    perform_undo,
    plan_duplicates,
    seed_demo_workspace,
)

logger = logging.getLogger(__name__)

# Backward-compatible names from v1.0 (banner moved to ui.py, demo seeding to workflows.py)
print_banner = ui.banner


class QuitApp(Exception):
    """Raised by the exit handler to leave the menu loop (instead of calling sys.exit in library code)."""


@dataclass
class AppContext:
    persistence: PersistenceManager

    def make_engine(self, strategy_name: str = "type") -> FileOrganizerEngine:
        """Engine that never touches the application's own history / log files."""
        return FileOrganizerEngine(
            strategy=get_strategy(strategy_name), exclude_paths=self.persistence.state_files()
        )


def _offer_recovery(engine: FileOrganizerEngine, target_dir: str) -> None:
    """If a previous run crashed mid-batch, offer to undo its partial moves."""
    if engine.has_pending_journal(target_dir):
        ui.warning("\n[Recovery] A previous run in this folder did not finish (crash or power loss).")
        if prompt_yes_no("Restore the partially moved files now? (y/n): "):
            restored, failed, errors = engine.recover_pending(target_dir)
            ui.show_rollback_result(restored, failed, errors)


def handle_organize(ctx: AppContext) -> None:
    ui.info("\n[Mode: Directory Organizer]")
    target_dir = prompt_existing_directory("Enter full directory path to organize: ")

    options = ", ".join(STRATEGY_NAMES)
    strategy_name = prompt_choice(STRATEGY_NAMES, f"Grouping strategy [{options}] (Enter = type): ", default="type")
    engine = ctx.make_engine(strategy_name)
    _offer_recovery(engine, target_dir)

    ui.info(f"\nScanning '{target_dir}'...")
    plan_summary = engine.summarize_plan(engine.iter_scan(target_dir))
    if plan_summary["total_files"] == 0:
        ui.warning("\n[Notice] No organize-able files detected in target folder.")
        return

    ui.show_preview(plan_summary)
    if not prompt_yes_no("Execute file relocations now? (y/n): "):
        ui.warning("\n[Cancelled] Operation aborted by user. No files were modified.")
        return

    atomic = prompt_yes_no("All-or-nothing mode (undo everything if any file fails)? (y/n): ")
    try:
        summary = perform_organize(engine, ctx.persistence, target_dir, atomic=atomic)
    except KeyboardInterrupt:
        ui.warning("\n[Interrupted] The batch was reverted; no files were left half-moved.")
        return
    ui.show_operation_result(summary)


def handle_rollback(ctx: AppContext) -> None:
    ui.info("\n[Mode: Rollback / Undo]")
    candidates = ctx.persistence.get_rollbackable(5)
    if not candidates:
        ui.warning("\n[Info] No recorded operations found to rollback.")
        return

    ui.plain("\nRecent Operations Available for Rollback:")
    for idx, op in enumerate(candidates, start=1):
        files = sum(1 for r in op.get("moved_files", []) if r.get("status") == "SUCCESS")
        ui.plain(f" {idx}. ID: {op.get('operation_id')} | Date: {str(op.get('timestamp'))[:19]} "
                 f"| Path: {op.get('target_directory')} ({files} files)")

    selection = prompt_menu_choice(1, len(candidates), "Select operation index to undo: ")
    target_op = candidates[selection - 1]
    if prompt_yes_no("Are you sure you want to restore these files to their original paths? (y/n): "):
        engine = ctx.make_engine()
        ui.show_rollback_result(*perform_undo(engine, ctx.persistence, target_op))


def handle_search(ctx: AppContext) -> None:
    ui.info("\n[Mode: Search & Query Records]")
    analytics = AnalyticsEngine(ctx.persistence.load_history())
    keyword = prompt_text("Enter filename search keyword (leave empty for all): ")
    category = prompt_text("Enter category filter (leave empty for all): ")

    results = analytics.search_records(keyword=keyword, category=category)
    ui.success(f"\nFound {len(results)} matching records:")
    ui.plain(f"{'Filename':<30} | {'Category':<15} | {'Date':<19} | Operation ID")
    ui.plain("-" * 80)
    for record in results[:20]:
        ui.plain(f"{str(record.get('filename'))[:28]:<30} | {str(record.get('category')):<15} | "
                 f"{str(record.get('timestamp'))[:19]:<19} | {record.get('operation_id')}")
    if len(results) > 20:
        ui.plain(f"... {len(results) - 20} more not shown")


def handle_analytics(ctx: AppContext) -> None:
    ui.info("\n[Mode: Analytics & Report Export]")
    analytics = AnalyticsEngine(ctx.persistence.load_history())
    metrics = analytics.compute_metrics()

    ui.heading("\n=== PERFORMANCE METRICS ===")
    ui.plain(f" Total Operations:      {metrics['total_operations']}")
    ui.plain(f" Total Files Organized: {metrics['total_files_organized']}")
    ui.plain(f" Total Data Volume:     {metrics['total_volume_mb']} MB")
    ui.plain(f" Avg Files / Operation: {metrics['avg_files_per_operation']}")
    ui.plain(f" Rolled-back Files:     {metrics['status_breakdown']['ROLLED_BACK']}")

    ui.heading("\n--- Category Breakdown ---")
    for category, count in metrics["category_distribution"].items():
        ui.plain(f"  - {category:<20}: {count} files")

    try:
        report_file = analytics.export_markdown_report()
    except OSError as exc:
        ui.error(f"\n[Error] Could not write report: {exc}")
        return
    ui.success(f"\n[Success] Exported Markdown report to '{report_file}'!")


def handle_demo(ctx: AppContext) -> None:
    ui.info("\n[Mode: Automated Hackathon Live Demo]")
    demo_folder = seed_demo_workspace()
    ui.success(f"Created demo workspace with sample files: '{demo_folder}'")

    engine = ctx.make_engine()
    ui.show_preview(engine.summarize_plan(engine.iter_scan(demo_folder)))
    ui.show_dry_run_result(engine.execute_organization(demo_folder, engine.iter_scan(demo_folder), dry_run=True), max_rows=5)

    ui.info("Executing automated demo organization...")
    summary = perform_organize(engine, ctx.persistence, demo_folder, atomic=True)
    report_file = AnalyticsEngine(ctx.persistence.load_history()).export_markdown_report()
    ui.success(f"\n[DEMO COMPLETE] Organized {summary['successful_moves']} files and generated executive report "
               f"'{report_file}'. Use option 2 to undo it, or option 6 to detect the duplicate System_Logs file.")


def handle_duplicates(ctx: AppContext) -> None:
    ui.info("\n[Mode: Duplicate File Finder]")
    root = prompt_existing_directory("Enter full directory path to scan for duplicates: ")
    ui.info("Scanning and hashing same-size files...")
    groups, plan = plan_duplicates(root, recursive=True, exclude=ctx.persistence.state_files())
    if not groups:
        ui.success("\n[Info] No duplicate files found.")
        return

    ui.warning(f"\nFound {len(groups)} duplicate group(s); {len(plan)} redundant copies:")
    for group in groups[:10]:
        ui.plain(f"  KEEP  {group[0]}")
        for duplicate in group[1:]:
            ui.plain(f"  MOVE  {duplicate}")
    if len(groups) > 10:
        ui.plain(f"  ... {len(groups) - 10} more group(s)")

    if prompt_yes_no("Move redundant copies into a 'Duplicates' folder (undo-able)? (y/n): "):
        summary = perform_quarantine(ctx.make_engine(), ctx.persistence, root, plan)
        ui.show_operation_result(summary)
    else:
        ui.warning("\n[Cancelled] No files were modified.")


def handle_exit(ctx: AppContext) -> None:
    ui.plain("")
    ui.plain("Thank you for using File Organizer Assistant! Goodbye.\n")
    raise QuitApp


MENU: Dict[int, Tuple[str, Callable[[AppContext], None]]] = {
    1: ("Organize Target Directory (Interactive Preview & Sorting)", handle_organize),
    2: ("Rollback / Undo Previous Operation", handle_rollback),
    3: ("Query & Search Past Record Operations", handle_search),
    4: ("View Performance Analytics & Export Summary Report", handle_analytics),
    5: ("Run Automated Hackathon Demo (Seed Sample Workspace)", handle_demo),
    6: ("Find & Quarantine Duplicate Files", handle_duplicates),
    7: ("Exit Application", handle_exit),
}


def main(persistence: Optional[PersistenceManager] = None) -> None:
    """Runs the interactive menu loop."""
    setup_logging()
    ctx = AppContext(persistence=persistence or PersistenceManager())
    logger.info("Interactive session started.")

    while True:
        ui.banner()
        ui.heading("\n--- MAIN MENU ---")
        for number, (label, _) in MENU.items():
            ui.plain(f" {number}. {label}")
        ui.plain("-" * 50)

        try:
            choice = prompt_menu_choice(1, len(MENU), f"Enter menu option [1-{len(MENU)}]: ")
        except (KeyboardInterrupt, EOFError):
            ui.plain("\nGoodbye.")
            return

        try:
            MENU[choice][1](ctx)
            input("\nPress Enter to return to main menu...")
        except QuitApp:
            return
        except KeyboardInterrupt:
            ui.warning("\n[Cancelled] Returning to main menu.")
        except EOFError:
            ui.plain("\nInput closed. Goodbye.")
            return
        except OSError as exc:
            logger.exception("Unexpected I/O failure in menu option %s", choice)
            ui.error(f"\n[Error] File system problem: {exc}")


if __name__ == "__main__":
    main()
