import os
import shutil
import tempfile
import unittest

from helpers import make_file  # noqa: F401
from file_organizer.analytics import AnalyticsEngine


class TestAnalytics(unittest.TestCase):
    def setUp(self):
        self.sample_history = [
            {
                "operation_id": "OP-1",
                "timestamp": "2026-11-21T10:00:00",
                "target_directory": "/tmp/test",
                "total_files_processed": 2,
                "successful_moves": 2,
                "failed_moves": 0,
                "moved_files": [
                    {"filename": "doc.pdf", "category": "Documents", "size_bytes": 1048576, "status": "SUCCESS"},
                    {"filename": "img.png", "category": "Images", "size_bytes": 2097152, "status": "SUCCESS"},
                ],
            }
        ]
        self.analytics = AnalyticsEngine(self.sample_history)

    def test_compute_metrics(self):
        metrics = self.analytics.compute_metrics()
        self.assertEqual(metrics["total_operations"], 1)
        self.assertEqual(metrics["total_files_organized"], 2)
        self.assertEqual(metrics["total_volume_mb"], 3.0)
        self.assertEqual(metrics["category_distribution"]["Documents"], 1)

    def test_metrics_on_empty_history(self):
        metrics = AnalyticsEngine([]).compute_metrics()
        self.assertEqual(metrics["total_operations"], 0)
        self.assertEqual(metrics["avg_files_per_operation"], 0)

    def test_metrics_separate_failed_and_rolled_back(self):
        history = [{"operation_id": "OP-2", "moved_files": [
            {"filename": "a", "category": "X", "size_bytes": 5, "status": "SUCCESS"},
            {"filename": "b", "category": "X", "size_bytes": 5, "status": "FAILED: nope"},
            {"filename": "c", "category": "X", "size_bytes": 5, "status": "ROLLED_BACK"},
            {"filename": "d", "category": "X", "size_bytes": 5, "status": "PLANNED"},
        ]}]
        metrics = AnalyticsEngine(history).compute_metrics()
        self.assertEqual(metrics["status_breakdown"], {"SUCCESS": 1, "FAILED": 1, "ROLLED_BACK": 1})
        self.assertEqual(metrics["total_files_organized"], 1)

    def test_search_records(self):
        res = self.analytics.search_records(keyword="doc")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["filename"], "doc.pdf")
        self.assertEqual(res[0]["operation_id"], "OP-1")
        self.assertEqual(len(self.analytics.search_records(category="images")), 1)
        self.assertEqual(len(self.analytics.search_records()), 2)
        self.assertEqual(self.analytics.search_records(keyword="zzz"), [])

    def test_export_markdown_report(self):
        temp_dir = tempfile.mkdtemp()
        try:
            out = self.analytics.export_markdown_report(os.path.join(temp_dir, "test_report.md"))
            self.assertTrue(os.path.exists(out))
            with open(out, encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("| Documents | 1 | 50.0% |", text)
            self.assertIn("OP-1", text)
        finally:
            shutil.rmtree(temp_dir)

    def test_report_tolerates_missing_timestamp_and_rolled_back(self):
        history = [{"operation_id": "OP-X", "target_directory": "/t", "rolled_back": True, "moved_files": []}]
        text = AnalyticsEngine(history).build_markdown_report()
        self.assertIn("N/A", text)
        self.assertIn("Rolled back", text)

    def test_export_raises_oserror_for_bad_path(self):
        with self.assertRaises(OSError):
            self.analytics.export_markdown_report("/nonexistent_dir_xyz/report.md")


if __name__ == "__main__":
    unittest.main()
