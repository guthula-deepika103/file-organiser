"""
Defensive input validation module for File Organizer Assistant.

Pure validators (``validate_directory``) raise ``ValueError``; the ``prompt_*``
helpers wrap them in retry loops. Ctrl+C and EOF (closed stdin) are never
swallowed - they propagate so callers can exit cleanly instead of looping forever.
"""

import re
from pathlib import Path
from typing import Optional, Sequence

from . import ui
from .pathutils import is_protected_path, normalize

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def validate_directory(raw_path: str) -> Path:
    """
    Normalises and validates a user supplied folder path.
    Raises ValueError with a user-friendly message when it is unusable.
    """
    cleaned = (raw_path or "").strip().strip('"').strip("'")
    if not cleaned:
        raise ValueError("Path cannot be blank. Please enter a valid directory.")
    if "\x00" in cleaned:
        raise ValueError("Path contains invalid characters.")
    path = normalize(cleaned)
    if not path.exists():
        raise ValueError(f"Directory '{path}' does not exist.")
    if not path.is_dir():
        raise ValueError(f"Path '{path}' is a file, not a directory.")
    if is_protected_path(path):
        raise ValueError(f"'{path}' is a protected system location and cannot be organized.")
    return path


def sanitize_text(raw: str, max_length: int = 100) -> str:
    """Strips control characters and caps the length of free-text input."""
    return _CONTROL_CHARS.sub("", raw).strip()[:max_length]


def prompt_existing_directory(prompt_msg: str = "Enter target directory path: ") -> str:
    """Loops until a valid, existing, non-protected directory path is entered."""
    while True:
        try:
            return str(validate_directory(input(prompt_msg)))
        except ValueError as exc:
            ui.error(f"[Error] {exc}")


def prompt_menu_choice(min_val: int, max_val: int, prompt_msg: str = "Select an option: ") -> int:
    """Loops until a valid integer within [min_val, max_val] is selected."""
    while True:
        raw = input(prompt_msg).strip()
        if not raw:
            ui.error("[Error] Selection cannot be empty.")
            continue
        try:
            value = int(raw)
        except ValueError:
            ui.error("[Error] Invalid input. Please enter a valid number.")
            continue
        if min_val <= value <= max_val:
            return value
        ui.error(f"[Error] Selection must be between {min_val} and {max_val}.")


def prompt_yes_no(prompt_msg: str = "Do you want to proceed? (y/n): ") -> bool:
    """Loops until a valid yes/no response is entered."""
    while True:
        answer = input(prompt_msg).strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        ui.error("[Error] Please answer 'y' or 'n'.")


def prompt_text(prompt_msg: str, max_length: int = 100) -> str:
    """Free-text prompt (may be empty); control characters are stripped."""
    return sanitize_text(input(prompt_msg), max_length)


def prompt_choice(options: Sequence[str], prompt_msg: str, default: Optional[str] = None) -> str:
    """Asks for one of ``options`` by name; an empty answer picks ``default`` if given."""
    lowered = {opt.lower(): opt for opt in options}
    while True:
        answer = input(prompt_msg).strip().lower()
        if not answer and default is not None:
            return default
        if answer in lowered:
            return lowered[answer]
        ui.error(f"[Error] Please choose one of: {', '.join(options)}.")

