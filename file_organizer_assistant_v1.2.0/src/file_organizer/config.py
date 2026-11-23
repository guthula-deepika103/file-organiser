"""
Configuration and constants for File Organizer Assistant (Project #105).

Provides the default categorization map, validation / loading of custom rule
files, ANSI colour helpers and filesystem defaults.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Union

logger = logging.getLogger(__name__)


class ConfigError(ValueError):
    """Raised when a category-rule configuration is malformed."""


# Default categorization mapping based on file extensions.
# NOTE: an extension must belong to exactly one category (".sh" used to be in
# two categories, which made the second mapping unreachable).
DEFAULT_CATEGORY_MAP: Dict[str, List[str]] = {
    "Documents": [".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt", ".epub", ".pages", ".md"],
    "Spreadsheets": [".xlsx", ".xls", ".csv", ".tsv", ".ods"],
    "Presentations": [".pptx", ".ppt", ".key", ".odp"],
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".ico"],
    "Audio_Video": [".mp3", ".wav", ".aac", ".flac", ".mp4", ".mkv", ".mov", ".avi", ".wmv"],
    "Code_Development": [".py", ".js", ".html", ".css", ".json", ".xml", ".java", ".cpp", ".c", ".sh", ".sql", ".rs", ".go"],
    "Archives": [".zip", ".tar", ".gz", ".7z", ".rar", ".bz2"],
    "Executables_Installers": [".exe", ".dmg", ".pkg", ".deb", ".msi"],
}

UNKNOWN_CATEGORY = "Others_Unsorted"
DUPLICATES_CATEGORY = "Duplicates"

# Persistence / logging file defaults
DEFAULT_JSON_PERSISTENCE = "organizer_history.json"
DEFAULT_CSV_AUDIT_LOG = "organizer_audit.csv"
DEFAULT_LOG_FILE = "organizer.log"

# Write-ahead journal used for crash recovery (hidden file inside target dir)
JOURNAL_FILENAME = ".organizer_journal.jsonl"
DEMO_MARKER_FILENAME = ".organizer_demo"

MAX_CATEGORY_NAME_LENGTH = 64


# ANSI Terminal Color Formatting
class TerminalColors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def colors_enabled() -> bool:
    """Colours are disabled when the NO_COLOR convention variable is set."""
    return "NO_COLOR" not in os.environ


def colorize(text: str, color_code: str) -> str:
    """Wrap text in ANSI color escape sequences (no-op when NO_COLOR is set)."""
    if not colors_enabled():
        return text
    return f"{color_code}{text}{TerminalColors.ENDC}"


def is_safe_category_name(name: object) -> bool:
    """A category becomes a folder name, so it must not be able to escape the target dir."""
    if not isinstance(name, str) or not name or name != name.strip():
        return False
    if name in (".", "..") or len(name) > MAX_CATEGORY_NAME_LENGTH:
        return False
    if any(ch in name for ch in '/\\:*?"<>|') or any(ord(ch) < 32 for ch in name):
        return False
    return True


def validate_category_map(category_map: object) -> Dict[str, List[str]]:
    """
    Validates a {category: [extensions]} mapping and returns a normalised copy
    (extensions lower-cased). Raises ConfigError describing the first problem.
    """
    if not isinstance(category_map, dict) or not category_map:
        raise ConfigError("Category map must be a non-empty JSON object.")

    normalised: Dict[str, List[str]] = {}
    seen: Dict[str, str] = {}
    for category, extensions in category_map.items():
        if not is_safe_category_name(category):
            raise ConfigError(f"Unsafe or invalid category name: {category!r}")
        if not isinstance(extensions, list) or not extensions:
            raise ConfigError(f"Category '{category}' must map to a non-empty list of extensions.")
        cleaned: List[str] = []
        for ext in extensions:
            if not isinstance(ext, str) or not ext.startswith(".") or len(ext) < 2 or "/" in ext or "\\" in ext:
                raise ConfigError(f"Invalid extension {ext!r} in category '{category}' (must look like '.pdf').")
            ext_lower = ext.lower()
            if ext_lower in seen and seen[ext_lower] != category:
                raise ConfigError(
                    f"Extension '{ext_lower}' is assigned to both '{seen[ext_lower]}' and '{category}'."
                )
            seen[ext_lower] = category
            cleaned.append(ext_lower)
        normalised[category] = cleaned
    return normalised


def build_extension_index(category_map: Dict[str, List[str]]) -> Dict[str, str]:
    """Inverts {category: [ext]} into {ext: category} for O(1) lookups."""
    index: Dict[str, str] = {}
    for category, extensions in category_map.items():
        for ext in extensions:
            key = ext.lower()
            if key in index and index[key] != category:
                logger.warning("Extension '%s' is mapped twice; keeping '%s'.", key, index[key])
                continue
            index[key] = category
    return index


def load_category_map(path: Union[str, Path]) -> Dict[str, List[str]]:
    """Loads and validates a custom category rule file (JSON)."""
    file_path = Path(path).expanduser()
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except OSError as exc:
        raise ConfigError(f"Cannot read config file '{file_path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config file '{file_path}' is not valid JSON: {exc}") from exc
    return validate_category_map(raw)
