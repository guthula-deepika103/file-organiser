#!/usr/bin/env python3
"""
Top-level launcher for File Organizer Assistant.

    python3 run_app.py                 # interactive menu
    python3 run_app.py organize PATH --dry-run
    python3 run_app.py --help
"""

import os
import sys

# Ensure the src/ directory is importable when run straight from the project folder
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from file_organizer.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
