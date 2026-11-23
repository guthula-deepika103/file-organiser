import csv
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from helpers import make_file  # noqa: F401  (sets sys.path)
from file_organizer.persistence import PersistenceManager


def sample_op(op_id="OP-TEST01", dry_run=False, status="SUCCESS", filename="test.txt"):
    return {
        "operation_id": op_id,
        "timestamp": "2026-11-21T20:00:00",
        "target_directory": "/tmp/x",
        "total_files_processed": 1,
        "successful_moves": 1,
        "failed_moves": 0,
        "dry_run": dry_run,
        "moved_files": [{
            "filename": filename, "source_dir": "/tmp/x", "target_dir": "/tmp/x/Documents",
            "category": "Documents", "size_bytes": 100, "status": status,
        }],
    }


class TestPersistence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.json_file = os.path.join(self.temp_dir, "test_history.json")
        self.csv_file = os.path.join(self.temp_dir, "test_audit.csv")
        self.pm = PersistenceManager(json_file=self.json_file, csv_file=self.csv_file)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_log_and_load_operation(self):
        self.assertTrue(self.pm.log_operation(sample_op()))
        history = self.pm.load_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["operation_id"], "OP-TEST01")
        with open(self.csv_file, newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(len(rows), 2)  # header + one file
        self.assertEqual(rows[1][2], "test.txt")

    def test_dry_run_is_not_persisted(self):
        self.assertFalse(self.pm.log_operation(sample_op(dry_run=True)))
        self.assertEqual(self.pm.load_history(), [])

    def test_corrupt_json_recovery(self):
        with open(self.json_file, "w") as f:
            f.write("CORRUPTED_NON_JSON_DATA{{{")
        recovered = PersistenceManager(json_file=self.json_file, csv_file=self.csv_file)
        self.assertEqual(recovered.load_history(), [])
        self.assertTrue(os.path.exists(self.json_file + ".corrupted.bak"))

    def test_wrong_json_shape_is_recovered(self):
        with open(self.json_file, "w") as f:
            json.dump({"not": "a list"}, f)
        recovered = PersistenceManager(json_file=self.json_file, csv_file=self.csv_file)
        self.assertEqual(recovered.load_history(), [])

    def test_load_history_survives_deleted_file(self):
        os.remove(self.json_file)
        self.assertEqual(self.pm.load_history(), [])

    def test_save_is_atomic_when_serialisation_fails(self):
        self.pm.log_operation(sample_op())
        self.assertFalse(self.pm.save_history([{"bad": object()}]))
        self.assertEqual(len(self.pm.load_history()), 1, "old content must survive a failed write")
        leftovers = [n for n in os.listdir(self.temp_dir) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_save_failure_returns_false(self):
        with mock.patch("file_organizer.persistence.os.replace", side_effect=OSError("boom")):
            self.assertFalse(self.pm.save_history([]))

    def test_csv_formula_injection_is_neutralised(self):
        self.pm.log_operation(sample_op(filename="=HYPERLINK(\"http://evil\")"))
        with open(self.csv_file, newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertTrue(rows[1][2].startswith("'="))

    def test_update_and_rollbackable(self):
        self.pm.log_operation(sample_op("OP-1"))
        self.pm.log_operation(sample_op("OP-2"))
        self.assertEqual([o["operation_id"] for o in self.pm.get_rollbackable(5)], ["OP-2", "OP-1"])
        op = self.pm.find_operation("op-1")
        op["rolled_back"] = True
        self.assertTrue(self.pm.update_operation(op))
        self.assertEqual([o["operation_id"] for o in self.pm.get_rollbackable(5)], ["OP-2"])
        self.assertFalse(self.pm.update_operation({"operation_id": "OP-MISSING"}))
        self.assertIsNone(self.pm.find_operation("OP-MISSING"))

    def test_log_rollback_adds_audit_rows(self):
        op = sample_op()
        self.pm.log_operation(op)
        self.assertTrue(self.pm.log_rollback(op, op["moved_files"]))
        with open(self.csv_file, newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows[-1][-1], "ROLLED_BACK")

    def test_state_files_lists_app_owned_files(self):
        names = {os.path.basename(str(p)) for p in self.pm.state_files()}
        self.assertTrue({"test_history.json", "test_audit.csv", "organizer.log"} <= names)


if __name__ == "__main__":
    unittest.main()
