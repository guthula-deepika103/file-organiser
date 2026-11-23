"""
Write-ahead move journal providing crash safety for batch file operations.

Before every move the engine appends ``{"src", "dst"}`` to a hidden JSON-lines
journal inside the target directory. If the process is killed mid-batch the
journal survives and ``FileOrganizerEngine.recover_pending`` can put the
already-moved files back. After a clean finish the journal is deleted.
"""

import json
import logging
import os
from pathlib import Path
from typing import IO, List, Optional, Tuple, Union

from .config import JOURNAL_FILENAME

logger = logging.getLogger(__name__)

_FSYNC_EVERY = 100  # fsync batching keeps journaling cheap for very large batches


class MoveJournal:
    def __init__(self, directory: Union[str, Path]):
        self.path = Path(directory) / JOURNAL_FILENAME
        self._handle: Optional[IO[str]] = None
        self._pending_sync = 0

    # ------------------------------------------------------------------ write
    def record(self, src: Path, dst: Path) -> None:
        """Durably notes an *intended* move (called before the move happens)."""
        if self._handle is None:
            self._handle = self.path.open("a", encoding="utf-8")
        self._handle.write(json.dumps({"src": str(src), "dst": str(dst)}) + "\n")
        self._handle.flush()
        self._pending_sync += 1
        if self._pending_sync >= _FSYNC_EVERY:
            os.fsync(self._handle.fileno())
            self._pending_sync = 0

    def commit(self) -> None:
        """Batch finished (or fully reverted): close and delete the journal."""
        self.close()
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("Could not remove journal '%s': %s", self.path, exc)

    def close(self) -> None:
        if self._handle is not None:
            try:
                self._handle.flush()
                os.fsync(self._handle.fileno())
            except OSError as exc:
                logger.debug("Journal sync failed: %s", exc)
            finally:
                self._handle.close()
                self._handle = None

    # ------------------------------------------------------------------- read
    def has_pending(self) -> bool:
        try:
            return self.path.is_file() and self.path.stat().st_size > 0
        except OSError:
            return False

    def read_entries(self) -> List[Tuple[Path, Path]]:
        """Returns journaled moves in order; a torn last line (crash) is ignored."""
        entries: List[Tuple[Path, Path]] = []
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entries.append((Path(data["src"]), Path(data["dst"])))
                    except (json.JSONDecodeError, KeyError, TypeError) as exc:
                        logger.warning("Ignoring unreadable journal line %d: %s", line_no, exc)
        except FileNotFoundError:
            return []
        except OSError as exc:
            logger.error("Cannot read journal '%s': %s", self.path, exc)
        return entries
