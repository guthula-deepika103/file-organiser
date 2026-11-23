import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import make_file
from file_organizer import config
from file_organizer.config import ConfigError, load_category_map, validate_category_map
from file_organizer.pathutils import is_protected_path, is_within, prune_empty_dirs, unique_destination
from file_organizer.strategies import DateStrategy, ExtensionStrategy, SizeStrategy, get_strategy
from file_organizer.transaction import MoveJournal


class TestConfig(unittest.TestCase):
    def test_default_map_is_valid_and_has_no_duplicate_extensions(self):
        validate_category_map(config.DEFAULT_CATEGORY_MAP)
        seen = [e for exts in config.DEFAULT_CATEGORY_MAP.values() for e in exts]
        self.assertEqual(len(seen), len(set(seen)))

    def test_validation_errors(self):
        bad_maps = [
            {}, [], {"A": []}, {"A": ["pdf"]}, {"A/B": [".x"]}, {"..": [".x"]}, {"": [".x"]},
            {"A": [".x"], "B": [".X"]}, {"A": "not a list"}, {"A": [".a/b"]}, {" A": [".x"]},
        ]
        for bad in bad_maps:
            with self.subTest(bad=bad):
                with self.assertRaises(ConfigError):
                    validate_category_map(bad)

    def test_load_from_file(self):
        tmp = tempfile.mkdtemp()
        try:
            good = os.path.join(tmp, "rules.json")
            with open(good, "w") as fh:
                json.dump({"Music": [".MP3", ".flac"]}, fh)
            self.assertEqual(load_category_map(good), {"Music": [".mp3", ".flac"]})
            broken = os.path.join(tmp, "broken.json")
            with open(broken, "w") as fh:
                fh.write("{nope")
            with self.assertRaises(ConfigError):
                load_category_map(broken)
            with self.assertRaises(ConfigError):
                load_category_map(os.path.join(tmp, "missing.json"))
        finally:
            shutil.rmtree(tmp)

    def test_colorize_respects_no_color(self):
        old = os.environ.get("NO_COLOR")
        try:
            os.environ["NO_COLOR"] = "1"
            self.assertEqual(config.colorize("x", config.TerminalColors.FAIL), "x")
            del os.environ["NO_COLOR"]
            self.assertIn("\033[", config.colorize("x", config.TerminalColors.FAIL))
        finally:
            if old is not None:
                os.environ["NO_COLOR"] = old
            else:
                os.environ["NO_COLOR"] = "1"


class TestPathUtils(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_is_within(self):
        self.assertTrue(is_within("/a/b/c", "/a/b"))
        self.assertTrue(is_within("/a/b", "/a/b"))
        self.assertFalse(is_within("/a/bc", "/a/b"))
        self.assertFalse(is_within("/a/b/../x", "/a/b"))

    def test_protected_paths(self):
        self.assertTrue(is_protected_path("/"))
        if os.name == "posix":
            self.assertTrue(is_protected_path("/etc"))
            self.assertTrue(is_protected_path("/usr/local"))
        self.assertFalse(is_protected_path(self.tmp))

    def test_unique_destination(self):
        folder = Path(self.tmp)
        make_file(folder, "a.txt")
        self.assertEqual(unique_destination(folder, "a.txt").name, "a_copy1.txt")
        self.assertEqual(unique_destination(folder, "a.txt", {str(folder / "a_copy1.txt")}).name, "a_copy2.txt")
        self.assertEqual(unique_destination(folder, "a.txt", tag="restored").name, "a_restored1.txt")
        self.assertEqual(unique_destination(folder, "new.txt").name, "new.txt")

    def test_prune_empty_dirs_stops_at_boundary(self):
        deep = Path(self.tmp) / "x" / "y"
        deep.mkdir(parents=True)
        prune_empty_dirs(deep, Path(self.tmp))
        self.assertFalse((Path(self.tmp) / "x").exists())
        self.assertTrue(Path(self.tmp).exists())
        keep = Path(self.tmp) / "k"
        keep.mkdir()
        make_file(keep, "f.txt")
        prune_empty_dirs(keep, Path(self.tmp))
        self.assertTrue(keep.exists())


class TestStrategies(unittest.TestCase):
    def test_factory(self):
        self.assertIsInstance(get_strategy("type"), ExtensionStrategy)
        self.assertIsInstance(get_strategy("DATE"), DateStrategy)
        self.assertIsInstance(get_strategy("size"), SizeStrategy)
        self.assertIsInstance(get_strategy(""), ExtensionStrategy)
        with self.assertRaises(ValueError):
            get_strategy("color")

    def test_size_buckets(self):
        import types
        strat = SizeStrategy()
        mk = lambda n: types.SimpleNamespace(st_size=n)  # noqa: E731
        self.assertEqual(strat.categorize(Path("x"), mk(10)), "Size_Small_Under_1MB")
        self.assertEqual(strat.categorize(Path("x"), mk(5 * 1024 * 1024)), "Size_Medium_1-100MB")
        self.assertEqual(strat.categorize(Path("x"), mk(500 * 1024 * 1024)), "Size_Large_Over_100MB")

    def test_date_strategy_handles_bad_timestamp(self):
        import types
        self.assertEqual(DateStrategy().categorize(Path("x"), types.SimpleNamespace(st_mtime=1e30)), "Unknown_Date")


class TestJournal(unittest.TestCase):
    def test_record_read_commit(self):
        tmp = tempfile.mkdtemp()
        try:
            journal = MoveJournal(tmp)
            self.assertFalse(journal.has_pending())
            journal.record(Path("/a"), Path("/b"))
            journal.close()
            self.assertTrue(journal.has_pending())
            self.assertEqual(journal.read_entries(), [(Path("/a"), Path("/b"))])
            journal.commit()
            self.assertFalse(journal.has_pending())
            self.assertEqual(journal.read_entries(), [])
            journal.commit()  # idempotent
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
