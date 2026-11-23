import contextlib
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import make_file
from file_organizer import cli, main as app_main, ui, validator
from file_organizer.core_engine import FileOrganizerEngine
from file_organizer.persistence import PersistenceManager
from file_organizer.workflows import perform_organize, perform_undo, plan_duplicates, seed_demo_workspace


def run_cli(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


class CliCase(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp()
        self.data = tempfile.mkdtemp()
        self.base = ["--data-dir", self.data]

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)
        shutil.rmtree(self.data, ignore_errors=True)

    def w(self, *parts):
        return os.path.join(self.work, *parts)


class TestCli(CliCase):
    def test_dry_run_leaves_files_alone(self):
        make_file(self.work, "a.pdf")
        code, out = run_cli(*self.base, "organize", self.work, "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("ENGINE DRY-RUN", out)
        self.assertTrue(os.path.exists(self.w("a.pdf")))

    def test_organize_then_undo(self):
        make_file(self.work, "a.pdf")
        make_file(self.work, "b.png")
        code, out = run_cli(*self.base, "organize", self.work, "--yes", "--atomic")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(self.w("Documents", "a.pdf")))
        code, out = run_cli(*self.base, "undo", "--yes")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(self.w("a.pdf")))
        code, out = run_cli(*self.base, "undo", "--yes")  # nothing left
        self.assertIn("No recorded operations", out)

    def test_undo_unknown_id_fails(self):
        code, out = run_cli(*self.base, "undo", "--id", "OP-NOPE", "--yes")
        self.assertEqual(code, 1)

    def test_organize_by_date_and_custom_config(self):
        make_file(self.work, "song.mp3")
        rules = make_file(self.data, "rules.json", '{"Music": [".mp3"]}')
        code, _ = run_cli(*self.base, "organize", self.work, "--yes", "--config", rules)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(self.w("Music", "song.mp3")))

    def test_invalid_inputs_return_error_codes(self):
        code, out = run_cli(*self.base, "organize", self.w("missing"), "--yes")
        self.assertEqual(code, 1)
        self.assertIn("does not exist", out)
        code, out = run_cli(*self.base, "organize", "/", "--yes")
        self.assertEqual(code, 1)
        self.assertIn("protected", out)
        make_file(self.work, "x.txt")
        bad = make_file(self.data, "bad.json", "{}")
        code, out = run_cli(*self.base, "organize", self.work, "--yes", "--config", bad)
        self.assertEqual(code, 1)

    def test_usage_error_exit_code(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                cli.main(["organize", self.work, "--strategy", "bogus"])
        self.assertEqual(ctx.exception.code, 2)

    def test_empty_folder_notice(self):
        code, out = run_cli(*self.base, "organize", self.work, "--yes")
        self.assertEqual(code, 0)
        self.assertIn("No organize-able files", out)

    def test_cancelled_by_prompt(self):
        make_file(self.work, "a.pdf")
        with mock.patch("builtins.input", return_value="n"):
            code, out = run_cli(*self.base, "organize", self.work)
        self.assertEqual(code, 0)
        self.assertIn("Cancelled", out)
        self.assertTrue(os.path.exists(self.w("a.pdf")))

    def test_history_and_stats(self):
        make_file(self.work, "report.pdf")
        run_cli(*self.base, "organize", self.work, "--yes")
        code, out = run_cli(*self.base, "history", "--keyword", "report")
        self.assertIn("report.pdf", out)
        report = os.path.join(self.data, "summary.md")
        code, out = run_cli(*self.base, "stats", "--report", report)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(report))

    def test_duplicates_command(self):
        make_file(self.work, "a.txt", "same")
        make_file(self.work, "b.txt", "same")
        code, out = run_cli(*self.base, "duplicates", self.work, "--dry-run")
        self.assertIn("KEEP", out)
        self.assertEqual(len(os.listdir(self.work)), 2)
        code, out = run_cli(*self.base, "duplicates", self.work, "--yes")
        self.assertEqual(code, 0)
        self.assertEqual(len(os.listdir(os.path.join(self.work, "Duplicates"))), 1)
        code, out = run_cli(*self.base, "duplicates", self.work, "--yes")
        self.assertIn("No duplicate", out)

    def test_interrupt_returns_130(self):
        make_file(self.work, "a.pdf")
        with mock.patch("builtins.input", side_effect=KeyboardInterrupt):
            code, _ = run_cli(*self.base, "organize", self.work)
        self.assertEqual(code, 130)

    def test_recovery_flow(self):
        make_file(self.work, "a.pdf")
        make_file(self.work, "b.png")
        engine = FileOrganizerEngine()
        import shutil as sh
        real = sh.move
        calls = {"n": 0}

        def crash(src, dst):
            calls["n"] += 1
            if calls["n"] == 2:
                raise SystemExit
            return real(src, dst)

        with mock.patch("file_organizer.core_engine.shutil.move", side_effect=crash):
            with self.assertRaises(SystemExit):
                engine.execute_organization(self.work, engine.iter_scan(self.work))
        code, out = run_cli(*self.base, "organize", self.work, "--yes", "--dry-run")
        self.assertIn("interrupted run", out)
        self.assertEqual(sorted(n for n in os.listdir(self.work) if not n.startswith(".")), ["a.pdf", "b.png"])


class TestWorkflowsAndMain(CliCase):
    def test_workflows_roundtrip(self):
        pm = PersistenceManager(os.path.join(self.data, "h.json"), os.path.join(self.data, "a.csv"))
        engine = FileOrganizerEngine()
        make_file(self.work, "a.pdf")
        summary = perform_organize(engine, pm, self.work)
        self.assertEqual(len(pm.load_history()), 1)
        restored, failed, _ = perform_undo(engine, pm, pm.find_operation(summary["operation_id"]))
        self.assertEqual((restored, failed), (1, 0))
        self.assertEqual(pm.get_rollbackable(), [])
        self.assertEqual(perform_organize(engine, pm, self.work)["successful_moves"], 1)
        groups, plan = plan_duplicates(self.work)
        self.assertEqual((groups, plan), ([], []))

    def test_seed_demo_is_repeatable_and_safe(self):
        demo = os.path.join(self.work, "demo")
        first = seed_demo_workspace(demo)
        engine = FileOrganizerEngine()
        engine.execute_organization(first, engine.iter_scan(first))
        again = seed_demo_workspace(demo)  # marker present -> reset
        self.assertTrue(os.path.exists(os.path.join(again, "Hackathon_Pitch_Deck.pptx")))
        self.assertFalse(os.path.exists(os.path.join(again, "Documents")))
        real_dir = os.path.join(self.work, "mine")
        make_file(real_dir, "important.txt")
        seed_demo_workspace(real_dir)  # no marker -> never wiped
        self.assertTrue(os.path.exists(os.path.join(real_dir, "important.txt")))

    def run_menu(self, inputs):
        pm = PersistenceManager(os.path.join(self.data, "h.json"), os.path.join(self.data, "a.csv"))
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=inputs), mock.patch.object(app_main, "setup_logging"), \
                contextlib.redirect_stdout(out):
            app_main.main(pm)
        return out.getvalue(), pm

    def test_menu_organize_and_rollback(self):
        make_file(self.work, "a.pdf")
        out, pm = self.run_menu(["1", self.work, "", "y", "n", "", "2", "1", "y", "", EOFError()])
        self.assertIn("Organized 1 files", out)
        self.assertIn("restored 1 files", out)
        self.assertTrue(os.path.exists(self.w("a.pdf")))

    def test_menu_validation_loops(self):
        out, _ = self.run_menu(["", "abc", "99", "7"])
        self.assertIn("cannot be empty", out)
        self.assertIn("valid number", out)
        self.assertIn("between 1 and 7", out)
        self.assertIn("Goodbye", out)

    def test_menu_search_analytics_demo_duplicates(self):
        make_file(self.work, "a.txt", "same")
        make_file(self.work, "b.txt", "same")
        cwd = os.getcwd()
        os.chdir(self.data)  # demo folder + report are created in cwd
        try:
            out, pm = self.run_menu([
                "5", "",                         # demo
                "3", "pitch", "", "",            # search
                "4", "",                         # analytics
                "6", self.work, "y", "",         # duplicates: quarantine
                "6", self.work, "",              # duplicates: nothing left
                "7",                             # exit option
            ])
        finally:
            os.chdir(cwd)
        self.assertIn("DEMO COMPLETE", out)
        self.assertIn("Found 1 matching records", out)
        self.assertIn("PERFORMANCE METRICS", out)
        self.assertIn("duplicate group", out)
        self.assertIn("No duplicate files found", out)

    def test_menu_ctrl_c_returns_to_menu(self):
        out, _ = self.run_menu(["1", KeyboardInterrupt(), "7"])
        self.assertIn("Returning to main menu", out)

    def test_menu_eof_exits(self):
        out, _ = self.run_menu([EOFError()])
        self.assertIn("Goodbye", out)


class TestValidatorAndUi(unittest.TestCase):
    def test_validate_directory(self):
        tmp = tempfile.mkdtemp()
        try:
            self.assertEqual(str(validator.validate_directory(f'"{tmp}"')), tmp)
            f = make_file(tmp, "f.txt")
            for bad in ("", "   ", f, os.path.join(tmp, "nope"), "/", "bad\x00path"):
                with self.subTest(bad=bad):
                    with self.assertRaises(ValueError):
                        validator.validate_directory(bad)
        finally:
            shutil.rmtree(tmp)

    def test_prompts_retry_until_valid(self):
        tmp = tempfile.mkdtemp()
        try:
            with mock.patch("builtins.input", side_effect=["", "/nope/x", tmp]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(validator.prompt_existing_directory(), tmp)
            with mock.patch("builtins.input", side_effect=["maybe", "YES"]), contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(validator.prompt_yes_no())
            with mock.patch("builtins.input", side_effect=["x", "n"]), contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(validator.prompt_yes_no())
            with mock.patch("builtins.input", side_effect=["color", "Date"]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(validator.prompt_choice(["type", "date"], "?"), "date")
            with mock.patch("builtins.input", return_value=""):
                self.assertEqual(validator.prompt_choice(["type", "date"], "?", default="type"), "type")
        finally:
            shutil.rmtree(tmp)

    def test_eof_and_ctrl_c_propagate_instead_of_looping(self):
        for exc in (EOFError, KeyboardInterrupt):
            with mock.patch("builtins.input", side_effect=exc):
                with self.assertRaises(exc):
                    validator.prompt_existing_directory()
                with self.assertRaises(exc):
                    validator.prompt_menu_choice(1, 3)
                with self.assertRaises(exc):
                    validator.prompt_yes_no()

    def test_sanitize_text(self):
        self.assertEqual(validator.sanitize_text("  hi\x1b[31m\x00there  "), "hi[31mthere")
        self.assertEqual(len(validator.sanitize_text("x" * 500)), 100)

    def test_render_preview(self):
        engine = FileOrganizerEngine()
        self.assertIn("No files found", ui.render_preview(engine.summarize_plan([])))
        plan = [{"filename": "f" * 50 + ".pdf", "category": "Documents", "size_bytes": 2048,
                 "source_path": "", "target_folder": "", "target_path": "", "extension": ".pdf"}] * 3
        text = ui.render_preview(engine.summarize_plan(plan, sample_size=1))
        self.assertIn("3 files", text)
        self.assertIn("... and 2 more", text)
        self.assertIn("...", text)  # long filename truncated
        self.assertIn("Documents: 3", text)

    def test_format_size(self):
        self.assertEqual(ui.format_size(10), "10 B")
        self.assertEqual(ui.format_size(2048), "2.0 KB")
        self.assertEqual(ui.format_size(5 * 1024 ** 3), "5.0 GB")

    def test_show_operation_result_variants(self):
        base = {"operation_id": "OP-1", "successful_moves": 1, "failed_moves": 0, "errors": []}
        for summary in (base, dict(base, failed_moves=1, errors=["boom"]), dict(base, aborted=True, failed_moves=1)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ui.show_operation_result(summary)
            self.assertIn("OP-1", buf.getvalue())

    def test_no_prints_outside_ui_and_cli(self):
        """Regression guard for the 'use logging instead of print' remark."""
        src = Path(__file__).resolve().parent.parent / "src" / "file_organizer"
        for path in src.glob("*.py"):
            if path.name == "ui.py":
                continue
            self.assertNotIn("print(", path.read_text(encoding="utf-8"), f"print() found in {path.name}")


if __name__ == "__main__":
    unittest.main()
