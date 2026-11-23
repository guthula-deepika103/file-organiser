"""
Central logging configuration.

Every module obtains ``logging.getLogger(__name__)`` (children of the
``file_organizer`` logger). Only user-facing terminal output lives in ``ui.py``;
diagnostics go through ``logging`` to a rotating log file (and optionally stderr).
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional, Union

from .config import DEFAULT_LOG_FILE

ROOT_LOGGER_NAME = "file_organizer"
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(
    verbose: bool = False,
    log_file: Optional[Union[str, Path]] = DEFAULT_LOG_FILE,
) -> logging.Logger:
    """
    Configures the package logger. Safe to call repeatedly (handlers are reset).

    verbose=True  -> DEBUG level and mirrored to stderr.
    log_file=None -> no file handler.
    """
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter(_LOG_FORMAT)

    if log_file:
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                str(log_file), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError as exc:  # read-only directory etc. - never crash because of logging
            sys.stderr.write(f"[warning] File logging disabled ({exc})\n")

    if verbose:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger
