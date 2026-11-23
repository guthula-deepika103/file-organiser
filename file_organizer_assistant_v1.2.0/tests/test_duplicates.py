import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from helpers import make_file
from file_organizer.core_engine import FileOrganizerEngine
from file_organizer.duplicates import (
    build_duplicate_plan, file_digest, find_duplicate_groups, iter_files, wasted_bytes,
)


class TestDuplicates(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_finds_identical_content_only(self):
        make_file(self.root, "a.txt", "same")
        make_file(self.root, "sub/b.txt", "same")
        make_file(self.root, "c.txt", "diff")      # same size, different content
        make_file(self.root, "empty1.txt", "")
        make_file(self.root, "empty2.txt", "")      # empties ignored
        groups = find_duplicate_groups(self.root)
        self.assertEqual(len(groups), 1)
        self.assertEqual({p.name for p in groups[0]}, {"a.txt", "b.txt"})

    def test_oldest_copy_is_kept(self):
        old = make_file(self.root, "z_old.txt", "dup")
        new = make_file(self.root, "a_new.txt", "dup")
        past = time.time() - 10_000
        os.utime(old, (past, past))
        groups = find_duplicate_groups(self.root)
        self.assertEqual(groups[0][0].name, "z_old.txt")
        plan = list(build_duplicate_plan(groups, self.root))
        self.assertEqual([p["filename"] for p in plan], ["a_new.txt"])
        self.assertEqual(wasted_bytes(groups), 3)
        self.assertTrue(os.path.exists(new))

    def test_non_recursive_and_hidden_and_quarantine_skipped(self):
        make_file(self.root, "a.txt", "x1")
        make_file(self.root, "sub/b.txt", "x1")
        make_file(self.root, ".hidden.txt", "x1")
        make_file(self.root, "Duplicates/old.txt", "x1")
        self.assertEqual(find_duplicate_groups(self.root, recursive=False), [])
        names = sorted(p.name for p in iter_files(self.root))
        self.assertEqual(names, ["a.txt", "b.txt"])

    def test_exclude_param(self):
        a = make_file(self.root, "a.txt", "x1")
        make_file(self.root, "b.txt", "x1")
        self.assertEqual(find_duplicate_groups(self.root, exclude=[Path(a)]), [])

    def test_digest_is_sha256(self):
        path = Path(make_file(self.root, "f.txt", "abc"))
        self.assertEqual(file_digest(path), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_quarantine_and_undo_through_engine(self):
        a = make_file(self.root, "a.txt", "dup")
        b = make_file(self.root, "sub/b.txt", "dup")
        past = time.time() - 5000
        os.utime(a, (past, past))
        groups = find_duplicate_groups(self.root)
        plan = list(build_duplicate_plan(groups, self.root))
        engine = FileOrganizerEngine()
        summary = engine.execute_organization(str(self.root), plan)
        self.assertEqual(summary["successful_moves"], 1)
        self.assertTrue(os.path.exists(a))
        self.assertFalse(os.path.exists(b))
        self.assertTrue((self.root / "Duplicates" / "b.txt").exists())
        succ, fail, _ = engine.rollback_operation(summary)
        self.assertEqual((succ, fail), (1, 0))
        self.assertTrue(os.path.exists(b))
        self.assertFalse((self.root / "Duplicates").exists())


if __name__ == "__main__":
    unittest.main()
