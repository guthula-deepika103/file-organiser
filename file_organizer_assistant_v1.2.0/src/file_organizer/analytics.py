"""
Analytics and report generation module for File Organizer Assistant.
Computes summary metrics, query filters, and exports Markdown executive summaries.
"""

import logging
import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Union

from .models import STATUS_PLANNED, STATUS_ROLLED_BACK, STATUS_SUCCESS, is_failed

logger = logging.getLogger(__name__)


def _short_timestamp(value: Any) -> str:
    return str(value)[:19] if value else "N/A"


class AnalyticsEngine:
    def __init__(self, history_records: List[Dict[str, Any]]):
        self.history = history_records

    def compute_metrics(self) -> Dict[str, Any]:
        """Aggregates stats across all recorded operations (rolled-back files are reported separately)."""
        total_ops = len(self.history)
        total_files = 0
        total_bytes = 0
        category_counts: Dict[str, int] = {}
        status_counts = {"SUCCESS": 0, "FAILED": 0, "ROLLED_BACK": 0}

        for op in self.history:
            for record in op.get("moved_files", []):
                status = record.get("status")
                if status == STATUS_SUCCESS:
                    status_counts["SUCCESS"] += 1
                    total_files += 1
                    total_bytes += record.get("size_bytes", 0)
                    category = record.get("category", "Uncategorized")
                    category_counts[category] = category_counts.get(category, 0) + 1
                elif status == STATUS_ROLLED_BACK:
                    status_counts["ROLLED_BACK"] += 1
                elif is_failed(status):
                    status_counts["FAILED"] += 1
                elif status != STATUS_PLANNED:
                    logger.debug("Unknown record status %r ignored in metrics.", status)

        avg_files_per_op = (total_files / total_ops) if total_ops else 0
        return {
            "total_operations": total_ops,
            "total_files_organized": total_files,
            "total_volume_mb": round(total_bytes / (1024 * 1024), 2),
            "avg_files_per_operation": round(avg_files_per_op, 1),
            "category_distribution": category_counts,
            "status_breakdown": status_counts,
        }

    def search_records(self, keyword: str = "", category: str = "") -> List[Dict[str, Any]]:
        """Filters file records by filename keyword and/or exact category."""
        matches: List[Dict[str, Any]] = []
        kw_lower = keyword.lower().strip()
        cat_lower = category.lower().strip()

        for op in self.history:
            for record in op.get("moved_files", []):
                match_kw = (not kw_lower) or (kw_lower in str(record.get("filename", "")).lower())
                match_cat = (not cat_lower) or (cat_lower == str(record.get("category", "")).lower())
                if match_kw and match_cat:
                    copy = dict(record)
                    copy["timestamp"] = op.get("timestamp")
                    copy["operation_id"] = op.get("operation_id")
                    matches.append(copy)
        return matches

    def build_markdown_report(self) -> str:
        """Renders the executive summary as Markdown text (pure function, no I/O)."""
        metrics = self.compute_metrics()
        status = metrics["status_breakdown"]
        lines = [
            "# File Organizer Assistant - Executive Summary Report",
            f"**Generated On:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ({platform.system() or 'unknown'} environment)",
            "",
            "## 1. Executive Performance Metrics",
            f"- **Total Operations Executed:** {metrics['total_operations']}",
            f"- **Total Files Organized:** {metrics['total_files_organized']}",
            f"- **Total Data Storage Managed:** {metrics['total_volume_mb']} MB",
            f"- **Average Files Per Batch:** {metrics['avg_files_per_operation']}",
            f"- **Successful File Relocations:** {status['SUCCESS']}",
            f"- **Failed File Relocations:** {status['FAILED']}",
            f"- **Relocations Rolled Back:** {status['ROLLED_BACK']}",
            "",
            "## 2. Category Distribution Breakdown",
            "| Category | Files Organized | Percentage |",
            "| :--- | :---: | :---: |",
        ]

        distribution = metrics["category_distribution"]
        total_cat_files = sum(distribution.values())
        for cat, count in sorted(distribution.items(), key=lambda item: item[1], reverse=True):
            pct = (count / total_cat_files * 100) if total_cat_files else 0.0
            lines.append(f"| {cat} | {count} | {pct:.1f}% |")

        lines.extend([
            "",
            "## 3. Recent Operation Logs",
            "| Operation ID | Timestamp | Target Directory | Files Processed | Status |",
            "| :--- | :--- | :--- | :---: | :--- |",
        ])
        for op in reversed(self.history[-10:]):
            if op.get("rolled_back"):
                status_str = "Rolled back"
            elif op.get("failed_moves", 0) == 0:
                status_str = "Completed"
            else:
                status_str = f"With {op.get('failed_moves')} Errors"
            lines.append(
                f"| {op.get('operation_id')} | {_short_timestamp(op.get('timestamp'))} "
                f"| `{op.get('target_directory')}` | {op.get('total_files_processed', 0)} | {status_str} |"
            )

        lines.extend([
            "",
            "---",
            "*Report auto-generated by File Organizer Assistant (SmartCommunity Hack Project #105)*",
        ])
        return "\n".join(lines)

    def export_markdown_report(self, output_filepath: Union[str, Path] = "organizer_executive_summary.md") -> str:
        """Writes the Markdown report to disk and returns the path. Raises OSError on I/O failure."""
        path = Path(output_filepath)
        path.write_text(self.build_markdown_report(), encoding="utf-8")
        logger.info("Executive summary exported to '%s'.", path)
        return str(path)
