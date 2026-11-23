"""
Pluggable categorisation strategies (Strategy design pattern).

The engine only depends on the ``CategorizationStrategy`` interface, so new
ways of grouping files (by type, modification month, size ...) can be added
without touching the scanning / moving / rollback code.
"""

import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .config import DEFAULT_CATEGORY_MAP, UNKNOWN_CATEGORY, build_extension_index

MIB = 1024 * 1024


class CategorizationStrategy(ABC):
    """Decides the destination sub-folder name for a file."""

    name = "base"
    description = ""

    @abstractmethod
    def categorize(self, path: Path, stat_result: os.stat_result) -> str:
        """Returns a safe folder name for the given file."""


class ExtensionStrategy(CategorizationStrategy):
    """Groups files by extension using an O(1) extension -> category index."""

    name = "type"
    description = "Group by file type (Documents, Images, ...)"

    def __init__(self, category_map: Optional[Dict[str, List[str]]] = None):
        self.category_map = category_map or DEFAULT_CATEGORY_MAP
        self._index = build_extension_index(self.category_map)

    def category_for_extension(self, ext: str) -> str:
        return self._index.get(ext.lower(), UNKNOWN_CATEGORY)

    def categorize(self, path: Path, stat_result: os.stat_result) -> str:
        return self.category_for_extension(os.path.splitext(path.name)[1])


class DateStrategy(CategorizationStrategy):
    """Groups files by modification month, e.g. ``2026-11``."""

    name = "date"
    description = "Group by last-modified month (YYYY-MM)"
    UNKNOWN = "Unknown_Date"

    def categorize(self, path: Path, stat_result: os.stat_result) -> str:
        try:
            return datetime.fromtimestamp(stat_result.st_mtime).strftime("%Y-%m")
        except (OverflowError, OSError, ValueError):
            return self.UNKNOWN


class SizeStrategy(CategorizationStrategy):
    """Groups files into Small / Medium / Large buckets."""

    name = "size"
    description = "Group by size (<1 MB, 1-100 MB, >100 MB)"

    def categorize(self, path: Path, stat_result: os.stat_result) -> str:
        size = stat_result.st_size
        if size < MIB:
            return "Size_Small_Under_1MB"
        if size < 100 * MIB:
            return "Size_Medium_1-100MB"
        return "Size_Large_Over_100MB"


STRATEGY_NAMES = ("type", "date", "size")


def get_strategy(name: str, category_map: Optional[Dict[str, List[str]]] = None) -> CategorizationStrategy:
    """Factory used by the CLI / menu. Raises ValueError for unknown names."""
    key = (name or "type").strip().lower()
    if key == "type":
        return ExtensionStrategy(category_map)
    if key == "date":
        return DateStrategy()
    if key == "size":
        return SizeStrategy()
    raise ValueError(f"Unknown strategy '{name}'. Choose one of: {', '.join(STRATEGY_NAMES)}.")
