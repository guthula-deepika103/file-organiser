import os
import shutil
import tempfile
import types
import unittest
from unittest import mock

from helpers import make_file
from file_organizer.config import ConfigError
from file_organizer.core_engine import FileOrganizerEngine
from file_organizer.strategies import DateStrategy, SizeStrategy


class EngineTestCase(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.engine = FileOrganizerEngine()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def p(self, *parts):
        return os.path.join(self.test_dir, *parts)


class TestCategoryAndScan(EngineTestCase):
    def test_category_mapping(self):
        self.assertEqual(self.engine.get_category_for_extension(".pdf"), "Documents")
        self.assertEqual(self.engine.get_category_for_extension(".PNG"), "Images")
        self.assertEqual(self.engine.get_category_for_extension(".py"), "Code_Development")
        self.assertEqual(self.engine.get_category_for_extension(".sh"), "Code_Development")
        self.assertEqual(self.engine.get_category_for_extension(".unknown_ext"), "Others_Unsorted")

    def test_custom_map_is_validated(self):
        engine = FileOrganizerEngine({"Music": [".MP3"]})
        self.assertEqual(engine.get_category_for_extension(".mp3"), "Music")
        with self.assertRaises(ConfigError):
            FileOrganizerEngine({"../evil": [".txt"]})

    def test_iter_scan_is_a_lazy_generator(self):
        make_file(self.test_dir, "a.pdf")
        gen = self.engine.iter_scan(self.test_dir)
        self.assertIsInstance(gen, types.GeneratorType)
        self.assertEqual(next(gen)["filename"], "a.pdf")

    def test_scan_skips_dirs_hidden_symlinks_and_journal(self):
        make_file(self.test_dir, "keep.txt")
        make_file(self.test_dir, ".hidden")
        make_file(self.test_dir, ".organizer_journal.jsonl")
        os.makedirs(self.p("subfolder"))
        make_file(self.test_dir, "subfolder/inner.txt")
        try:
            os.symlink(self.p("keep.txt"), self.p("link.txt"))
        except (OSError, NotImplementedError):
            pass
        names = [i["filename"] for i in self.engine.scan_directory(self.test_dir)]
        self.assertEqual(names, ["keep.txt"])

    def test_include_hidden(self):
        make_file(self.test_dir, ".env")
        engine = FileOrganizerEngine(include_hidden=True)
        self.assertEqual([i["filename"] for i in engine.scan_directory(self.test_dir)], [".env"])

    def test_exclude_paths(self):
        make_file(self.test_dir, "organizer_history.json")
        make_file(self.test_dir, "real.txt")
        engine = FileOrganizerEngine(exclude_paths=[self.p("organizer_history.json")])
        self.assertEqual([i["filename"] for i in engine.scan_directory(self.test_dir)], ["real.txt"])

    def test_scan_missing_directory_yields_nothing(self):
        self.assertEqual(self.engine.scan_directory(self.p("nope")), [])

    def test_scan_directory_is_sorted(self):
        for name in ("b.txt", "a.txt", "c.txt"):
            make_file(self.test_dir, name)
        self.assertEqual([i["filename"] for i in self.engine.scan_directory(self.test_dir)], ["a.txt", "b.txt", "c.txt"])

    def test_no_extension_file(self):
        make_file(self.test_dir, "Makefile")
        item = self.engine.scan_directory(self.test_dir)[0]
        self.assertEqual(item["extension"], "[No Ext]")
        self.assertEqual(item["category"], "Others_Unsorted")

    def test_summarize_plan_streams_and_samples(self):
        for i in range(30):
            make_file(self.test_dir, f"f{i}.txt", "x" * 10)
        summary = self.engine.summarize_plan(self.engine.iter_scan(self.test_dir), sample_size=5)
        self.assertEqual(summary["total_files"], 30)
        self.assertEqual(summary["total_bytes"], 300)
        self.assertEqual(summary["by_category"], {"Documents": 30})
        self.assertEqual(len(summary["sample"]), 5)

    def test_strategies_choose_folder(self):
        make_file(self.test_dir, "small.bin", "x")
        item = FileOrganizerEngine(strategy=SizeStrategy()).scan_directory(self.test_dir)[0]
        self.assertEqual(item["category"], "Size_Small_Under_1MB")
        item = FileOrganizerEngine(strategy=DateStrategy()).scan_directory(self.test_dir)[0]
        self.assertRegex(item["category"], r"^\d{4}-\d{2}$")


class TestExecute(EngineTestCase):
    def test_scan_and_execute_organization(self):
        make_file(self.test_dir, "doc1.pdf")
        make_file(self.test_dir, "img1.png")
        plan = self.engine.scan_directory(self.test_dir)
        summary = self.engine.execute_organization(self.test_dir, plan)
        self.assertEqual(summary["successful_moves"], 2)
        self.assertEqual(summary["failed_moves"], 0)
        self.assertTrue(os.path.exists(self.p("Documents", "doc1.pdf")))
        self.assertTrue(os.path.exists(self.p("Images", "img1.png")))
        self.assertFalse(os.path.exists(self.p(".organizer_journal.jsonl")), "journal removed after clean run")

    def test_execute_accepts_generator_directly(self):
        make_file(self.test_dir, "a.pdf")
        summary = self.engine.execute_organization(self.test_dir, self.engine.iter_scan(self.test_dir))
        self.assertEqual(summary["successful_moves"], 1)

    def test_dry_run_changes_nothing(self):
        make_file(self.test_dir, "a.pdf")
        summary = self.engine.execute_organization(self.test_dir, self.engine.iter_scan(self.test_dir), dry_run=True)
        self.assertTrue(summary["dry_run"])
        self.assertEqual(summary["planned_moves"], 1)
        self.assertEqual(summary["successful_moves"], 0)
        self.assertEqual(summary["moved_files"][0]["status"], "PLANNED")
        self.assertTrue(os.path.exists(self.p("a.pdf")))
        self.assertFalse(os.path.exists(self.p("Documents")))
        self.assertFalse(os.path.exists(self.p(".organizer_journal.jsonl")))

    def test_dry_run_predicts_collisions_within_batch(self):
        plan = [
            {"filename": "x.txt", "extension": ".txt", "category": "Documents", "source_path": self.p("one", "x.txt"),
             "target_folder": self.p("Documents"), "target_path": self.p("Documents", "x.txt"), "size_bytes": 1},
            {"filename": "x.txt", "extension": ".txt", "category": "Documents", "source_path": self.p("two", "x.txt"),
             "target_folder": self.p("Documents"), "target_path": self.p("Documents", "x.txt"), "size_bytes": 1},
        ]
        summary = self.engine.execute_organization(self.test_dir, plan, dry_run=True)
        targets = [r["target_path"] for r in summary["moved_files"]]
        self.assertEqual(targets, [self.p("Documents", "x.txt"), self.p("Documents", "x_copy1.txt")])

    def test_filename_collision_never_overwrites(self):
        make_file(self.test_dir, "Documents/report.pdf", "OLD")
        make_file(self.test_dir, "report.pdf", "NEW")
        summary = self.engine.execute_organization(self.test_dir, self.engine.scan_directory(self.test_dir))
        self.assertEqual(summary["successful_moves"], 1)
        with open(self.p("Documents", "report.pdf")) as fh:
            self.assertEqual(fh.read(), "OLD")
        with open(self.p("Documents", "report_copy1.pdf")) as fh:
            self.assertEqual(fh.read(), "NEW")

    def test_failure_is_recorded_and_batch_continues(self):
        make_file(self.test_dir, "a.pdf")
        make_file(self.test_dir, "b.png")
        real_move = shutil.move

        def flaky(src, dst):
            if src.endswith("a.pdf"):
                raise PermissionError("denied")
            return real_move(src, dst)

        with mock.patch("file_organizer.core_engine.shutil.move", side_effect=flaky):
            summary = self.engine.execute_organization(self.test_dir, self.engine.scan_directory(self.test_dir))
        self.assertEqual(summary["successful_moves"], 1)
        self.assertEqual(summary["failed_moves"], 1)
        self.assertIn("denied", summary["errors"][0])
        self.assertTrue(os.path.exists(self.p("a.pdf")))

    def test_atomic_mode_reverts_everything_on_failure(self):
        make_file(self.test_dir, "a.pdf")
        make_file(self.test_dir, "b.png")
        make_file(self.test_dir, "c.txt")
        real_move = shutil.move
        state = {"calls": 0}

        def fail_on_third(src, dst):
            state["calls"] += 1
            if state["calls"] == 3:
                raise OSError("disk full")
            return real_move(src, dst)

        with mock.patch("file_organizer.core_engine.shutil.move", side_effect=fail_on_third):
            summary = self.engine.execute_organization(self.test_dir, self.engine.scan_directory(self.test_dir), atomic=True)
        self.assertTrue(summary["aborted"])
        self.assertEqual(summary["successful_moves"], 0)
        for name in ("a.pdf", "b.png", "c.txt"):
            self.assertTrue(os.path.exists(self.p(name)), name)
        self.assertFalse(os.path.exists(self.p("Documents")), "empty category folders pruned")
        self.assertFalse(os.path.exists(self.p(".organizer_journal.jsonl")))

    def test_keyboard_interrupt_reverts_batch(self):
        make_file(self.test_dir, "a.pdf")
        make_file(self.test_dir, "b.png")
        real_move = shutil.move
        state = {"calls": 0}

        def interrupt(src, dst):
            state["calls"] += 1
            if state["calls"] == 2:
                raise KeyboardInterrupt
            return real_move(src, dst)

        with mock.patch("file_organizer.core_engine.shutil.move", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.engine.execute_organization(self.test_dir, self.engine.scan_directory(self.test_dir))
        self.assertTrue(os.path.exists(self.p("a.pdf")))
        self.assertTrue(os.path.exists(self.p("b.png")))

    def test_crash_recovery_from_journal(self):
        make_file(self.test_dir, "a.pdf")
        make_file(self.test_dir, "b.png")
        real_move = shutil.move
        state = {"calls": 0}

        def hard_crash(src, dst):
            state["calls"] += 1
            if state["calls"] == 2:
                raise SystemExit("simulated power loss")  # not caught by the engine
            return real_move(src, dst)

        with mock.patch("file_organizer.core_engine.shutil.move", side_effect=hard_crash):
            with self.assertRaises(SystemExit):
                self.engine.execute_organization(self.test_dir, self.engine.scan_directory(self.test_dir))
        self.assertTrue(self.engine.has_pending_journal(self.test_dir))
        self.assertFalse(os.path.exists(self.p("a.pdf")), "first file was moved before the crash")

        restored, failed, errors = self.engine.recover_pending(self.test_dir)
        self.assertEqual((restored, failed, errors), (1, 0, []))
        self.assertTrue(os.path.exists(self.p("a.pdf")))
        self.assertTrue(os.path.exists(self.p("b.png")))
        self.assertFalse(self.engine.has_pending_journal(self.test_dir))

    def test_recover_ignores_journal_entries_outside_directory(self):
        outside = tempfile.mkdtemp()
        try:
            victim = make_file(outside, "victim.txt")
            journal = self.p(".organizer_journal.jsonl")
            with open(journal, "w") as fh:
                fh.write('{"src": "%s", "dst": "%s"}\n' % (self.p("x.txt"), victim))
                fh.write("{broken json\n")
            restored, failed, errors = self.engine.recover_pending(self.test_dir)
            self.assertEqual(restored, 0)
            self.assertEqual(failed, 1)
            self.assertTrue(os.path.exists(victim))
        finally:
            shutil.rmtree(outside)


class TestRollback(EngineTestCase):
    def test_rollback(self):
        f1 = make_file(self.test_dir, "report.docx", "report data")
        summary = self.engine.execute_organization(self.test_dir, self.engine.scan_directory(self.test_dir))
        self.assertFalse(os.path.exists(f1))

        succ, fail, errs = self.engine.rollback_operation(summary)
        self.assertEqual((succ, fail, errs), (1, 0, []))
        self.assertTrue(os.path.exists(f1))
        self.assertFalse(os.path.exists(self.p("Documents")), "empty category folder removed")
        self.assertTrue(summary["rolled_back"])
        self.assertEqual(summary["moved_files"][0]["status"], "ROLLED_BACK")

    def test_rollback_twice_is_harmless(self):
        make_file(self.test_dir, "a.pdf")
        summary = self.engine.execute_organization(self.test_dir, self.engine.scan_directory(self.test_dir))
        self.engine.rollback_operation(summary)
        self.assertEqual(self.engine.rollback_operation(summary), (0, 0, []))

    def test_rollback_never_overwrites_new_file(self):
        make_file(self.test_dir, "a.pdf", "ORIGINAL")
        summary = self.engine.execute_organization(self.test_dir, self.engine.scan_directory(self.test_dir))
        make_file(self.test_dir, "a.pdf", "NEWER")  # user created a new file with the same name
        succ, fail, _ = self.engine.rollback_operation(summary)
        self.assertEqual((succ, fail), (1, 0))
        with open(self.p("a.pdf")) as fh:
            self.assertEqual(fh.read(), "NEWER")
        with open(self.p("a_restored1.pdf")) as fh:
            self.assertEqual(fh.read(), "ORIGINAL")

    def test_rollback_reports_missing_file(self):
        make_file(self.test_dir, "a.pdf")
        summary = self.engine.execute_organization(self.test_dir, self.engine.scan_directory(self.test_dir))
        os.remove(self.p("Documents", "a.pdf"))
        succ, fail, errs = self.engine.rollback_operation(summary)
        self.assertEqual((succ, fail), (0, 1))
        self.assertIn("missing", errs[0])

    def test_rollback_refuses_tampered_paths(self):
        outside = tempfile.mkdtemp()
        try:
            victim = make_file(outside, "secret.txt")
            record = {
                "target_directory": self.test_dir,
                "moved_files": [{"filename": "secret.txt", "status": "SUCCESS",
                                 "target_path": victim, "source_path": self.p("stolen.txt")}],
            }
            succ, fail, errs = self.engine.rollback_operation(record)
            self.assertEqual((succ, fail), (0, 1))
            self.assertIn("outside", errs[0])
            self.assertTrue(os.path.exists(victim))
        finally:
            shutil.rmtree(outside)

    def test_rollback_skips_failed_records(self):
        record = {"target_directory": self.test_dir,
                  "moved_files": [{"filename": "x", "status": "FAILED: nope", "target_path": "a", "source_path": "b"}]}
        self.assertEqual(self.engine.rollback_operation(record), (0, 0, []))


if __name__ == "__main__":
    unittest.main()
