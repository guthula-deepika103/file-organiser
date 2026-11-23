"""
Terminal presentation layer - the ONLY module that prints to the console.

Status messages are also forwarded to ``logging`` so the log file contains a
complete trail. Rendering helpers (``render_*``) are pure functions returning
strings, which keeps them unit-testable.
"""

import logging
from typing import Any, Dict, List

from . import __version__
from .config import TerminalColors, colorize

logger = logging.getLogger(__name__)

WIDTH = 80


def _emit(text: str, color: str = "", level: int = 0) -> None:
    print(colorize(text, color) if color else text)
    if level:
        logger.log(level, text.strip())


def info(message: str) -> None:
    _emit(message, TerminalColors.OKCYAN, logging.INFO)


def success(message: str) -> None:
    _emit(message, TerminalColors.OKGREEN, logging.INFO)


def warning(message: str) -> None:
    _emit(message, TerminalColors.WARNING, logging.WARNING)


def error(message: str) -> None:
    _emit(message, TerminalColors.FAIL, logging.ERROR)


def heading(message: str) -> None:
    _emit(message, TerminalColors.BOLD)


def plain(message: str = "") -> None:
    _emit(message)


def banner() -> None:
    _emit("=" * WIDTH, TerminalColors.HEADER)
    _emit("   FILE ORGANIZER ASSISTANT (SmartCommunity Hack - Project #105)", TerminalColors.BOLD + TerminalColors.OKCYAN)
    _emit(f"   Production Release v{__version__} | Zero-Dependency Desktop Sorting Utility", TerminalColors.OKBLUE)
    _emit("=" * WIDTH, TerminalColors.HEADER)


def format_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} GB"  # pragma: no cover


def _truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 3] + "..."


def render_preview(plan_summary: Dict[str, Any], title: str = "INTERACTIVE DRY-RUN PREVIEW") -> str:
    """Formats the output of ``FileOrganizerEngine.summarize_plan``."""
    total = plan_summary["total_files"]
    if total == 0:
        return "[Info] No files found to organize in the specified folder."

    lines = [
        "=" * WIDTH,
        f"  {title} ({total} files, {format_size(plan_summary['total_bytes'])})",
        "=" * WIDTH,
        f"{'Filename':<30} | {'Category':<18} | {'Size':<10} | Target Subfolder",
        "-" * WIDTH,
    ]
    for item in plan_summary["sample"]:
        lines.append(
            f"{_truncate(item['filename'], 30):<30} | {_truncate(item['category'], 18):<18} | "
            f"{format_size(item['size_bytes']):<10} | /{item['category']}/"
        )
    hidden = total - len(plan_summary["sample"])
    if hidden > 0:
        lines.append(f"... and {hidden} more file(s) not shown")
    lines.append("-" * WIDTH)
    breakdown = ", ".join(
        f"{cat}: {count}" for cat, count in sorted(plan_summary["by_category"].items(), key=lambda kv: (-kv[1], kv[0]))
    )
    lines.append(f"Category summary -> {breakdown}")
    lines.append("=" * WIDTH)
    return "\n".join(lines)


def show_preview(plan_summary: Dict[str, Any], title: str = "INTERACTIVE DRY-RUN PREVIEW") -> None:
    text = render_preview(plan_summary, title)
    if plan_summary["total_files"] == 0:
        info("\n" + text)
        return
    _emit("\n" + text + "\n", TerminalColors.HEADER)


def render_dry_run_result(summary: Dict[str, Any], max_rows: int = 25) -> str:
    """Formats the result of ``execute_organization(dry_run=True)`` (final, collision-resolved targets)."""
    records: List[Dict[str, Any]] = summary["moved_files"]
    lines = [
        "=" * WIDTH,
        f"  ENGINE DRY-RUN {summary['operation_id']} - {summary['planned_moves']} planned move(s), nothing modified",
        "=" * WIDTH,
    ]
    for record in records[:max_rows]:
        lines.append(f"{_truncate(record['filename'], 34):<34} -> {record['target_path']}")
    if len(records) > max_rows:
        lines.append(f"... and {len(records) - max_rows} more")
    renamed = sum(1 for r in records if not r["target_path"].endswith(r["filename"]))
    if renamed:
        lines.append(f"{renamed} file(s) would be renamed to avoid name collisions.")
    lines.append("=" * WIDTH)
    return "\n".join(lines)


def show_dry_run_result(summary: Dict[str, Any], max_rows: int = 25) -> None:
    _emit(render_dry_run_result(summary, max_rows), TerminalColors.OKBLUE)


def show_operation_result(summary: Dict[str, Any]) -> None:
    if summary.get("aborted"):
        warning(f"\n[Aborted] Atomic batch stopped on first error; all moves were reverted ({summary['failed_moves']} failure(s)).")
    elif summary["failed_moves"]:
        warning(f"\n[Partial] Organized {summary['successful_moves']} files, {summary['failed_moves']} failed.")
    else:
        success(f"\n[Success] Organized {summary['successful_moves']} files into category subfolders!")
    for message in summary.get("errors", [])[:10]:
        error(f" - {message}")
    info(f"Operation logged as ID: {summary['operation_id']}")


def show_rollback_result(success_count: int, fail_count: int, errors: List[str]) -> None:
    success(f"\n[Rollback Complete] Successfully restored {success_count} files. (Failures: {fail_count})")
    for message in errors:
        error(f" - {message}")
