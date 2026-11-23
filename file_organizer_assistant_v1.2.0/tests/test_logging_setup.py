import logging
import os
import shutil
import tempfile
import unittest

from helpers import make_file  # noqa: F401
from file_organizer.logging_setup import ROOT_LOGGER_NAME, setup_logging


class TestLoggingSetup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        setup_logging(log_file=None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_writes_to_log_file_and_is_idempotent(self):
        path = os.path.join(self.tmp, "app.log")
        setup_logging(log_file=path)
        logger = setup_logging(log_file=path)  # second call must not duplicate handlers
        logging.getLogger(ROOT_LOGGER_NAME + ".test").info("hello-log")
        for handler in logger.handlers:
            handler.flush()
        self.assertEqual(len(logger.handlers), 1)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read().count("hello-log"), 1)

    def test_verbose_adds_stream_handler_and_debug_level(self):
        logger = setup_logging(verbose=True, log_file=None)
        self.assertEqual(logger.level, logging.DEBUG)
        self.assertTrue(any(isinstance(h, logging.StreamHandler) for h in logger.handlers))

    def test_unwritable_log_file_does_not_crash(self):
        logger = setup_logging(log_file=os.path.join(self.tmp, "no_such_dir", "x.log"))
        self.assertTrue(logger.handlers)  # falls back to NullHandler


if __name__ == "__main__":
    unittest.main()
