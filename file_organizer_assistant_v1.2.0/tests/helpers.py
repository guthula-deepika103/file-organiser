"""Shared test helpers."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
os.environ["NO_COLOR"] = "1"  # keep captured output free of ANSI codes


def make_file(folder, name, content="data"):
    path = os.path.join(str(folder), name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path
