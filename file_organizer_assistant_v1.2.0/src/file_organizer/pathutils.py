"""
Path safety helpers built on ``pathlib``: containment checks, protected-folder
detection and collision-free destination naming.
"""

import os
from pathlib import Path
from typing import Optional, Set, Union

PathLike = Union[str, "os.PathLike[str]"]

# System folders that must never be bulk-reorganised.
_PROTECTED_POSIX = ("/bin", "/boot", "/dev", "/etc", "/lib", "/lib32", "/lib64", "/proc", "/sbin", "/sys", "/usr")
_PROTECTED_POSIX_EXACT = ("/var", "/run", "/root", "/home", "/opt", "/srv", "/mnt", "/media")


def normalize(path: PathLike) -> Path:
    """Expands ``~`` and makes the path absolute without touching the filesystem."""
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def is_within(path: PathLike, base: PathLike) -> bool:
    """True when ``path`` is ``base`` itself or lives somewhere underneath it."""
    candidate, root = normalize(path), normalize(base)
    return candidate == root or root in candidate.parents


def is_protected_path(path: PathLike) -> bool:
    """True for filesystem roots and operating-system directories."""
    p = normalize(path)
    if p == Path(p.anchor):
        return True
    if os.name == "nt":
        protected = [os.environ.get("SystemRoot"), os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")]
        return any(item and is_within(p, item) for item in protected)
    if str(p) in _PROTECTED_POSIX_EXACT:
        return True
    return any(is_within(p, item) for item in _PROTECTED_POSIX)


def unique_destination(
    folder: Path,
    filename: str,
    reserved: Optional[Set[str]] = None,
    tag: str = "copy",
) -> Path:
    """
    Returns ``folder/filename`` or, if that name is taken (on disk or in the
    ``reserved`` set of names planned in a dry-run), ``name_<tag>N.ext``.
    """
    candidate = folder / filename
    stem, ext = os.path.splitext(filename)
    counter = 1
    while candidate.exists() or (reserved is not None and str(candidate) in reserved):
        candidate = folder / f"{stem}_{tag}{counter}{ext}"
        counter += 1
    return candidate


def prune_empty_dirs(start: Path, stop_at: Path) -> None:
    """Removes ``start`` and its empty parents, never touching ``stop_at`` or anything above it."""
    current = normalize(start)
    boundary = normalize(stop_at)
    while current != boundary and boundary in current.parents:
        try:
            current.rmdir()  # only succeeds when empty
        except OSError:
            return
        current = current.parent
