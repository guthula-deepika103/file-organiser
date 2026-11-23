# File Organizer Assistant (v1.2.0)
**SmartCommunity Hackathon - Project #105 | Domain: Digital Tools & Productivity**

A zero-dependency Python 3.8+ application that sorts cluttered folders into structured sub-folders. It ships as an interactive terminal menu **and** a scriptable command-line tool, with engine-level dry-run, crash-safe transactional moves, rollback/undo, duplicate detection, JSON/CSV persistence and analytics.

---

## What's new in v1.2.0
Every point of the v1.0.0 evaluation report was addressed - see [`CHANGELOG.md`](CHANGELOG.md) and the remark-by-remark table in [`ARCHITECTURE.md`](ARCHITECTURE.md).

| Evaluation remark | Resolution |
| :--- | :--- |
| Use `logging` instead of `print` | `logging` everywhere (rotating `organizer.log`); `print` exists only in `ui.py` (enforced by a unit test) |
| Generator-based scanning for scalability | `iter_scan()` is a generator; scan + preview of 100,000 files peaks at < 1 MB (list approach: ~58 MB) |
| Transactional file operations | write-ahead journal, `--atomic` all-or-nothing mode, auto-revert on Ctrl+C, crash recovery |
| Dry-run flag at engine level | `execute_organization(..., dry_run=True)` |
| Use `pathlib` | `pathlib` used for all path handling |
| Broad `except Exception` | replaced by specific `OSError`, `shutil.Error`, `json.JSONDecodeError`, ... |

## Key Features
- **Interactive menu + CLI** (`organize`, `undo`, `history`, `stats`, `duplicates`)
- **Pluggable grouping strategies** (Strategy pattern): by `type`, by `date` (YYYY-MM) or by `size`, plus custom JSON rule files
- **Engine-level dry-run** and memory-flat **generator scanning**
- **Transactional moves**: write-ahead journal, `--atomic` mode, Ctrl+C safe, crash recovery
- **Safe rollback**: never overwrites newer files, refuses paths outside the operation folder (tamper-proof), prunes empty folders, per-file status tracking
- **Duplicate finder**: size bucketing + chunked SHA-256; extra copies quarantined into `Duplicates/` with full undo
- **Atomic JSON persistence** (temp file + fsync + replace), corruption recovery, CSV audit log with formula-injection protection
- **Defensive validation**: protected system folders refused, symlinks/hidden files skipped, closed stdin handled
- **Analytics** with Markdown executive summary

## Quickstart
**Browser interface (no terminal typing):** double-click `start_web.bat` (Windows) or run `python3 run_app.py web`, then open http://127.0.0.1:5000 . Choose a folder -> Generate preview -> Organize -> Undo from "Recent operations". Standard library only, no Flask needed.

```bash
python3 run_app.py                                   # interactive menu

python3 run_app.py organize ~/Downloads --dry-run    # preview only
python3 run_app.py organize ~/Downloads --strategy date --atomic --yes
python3 run_app.py undo                              # undo latest operation
python3 run_app.py duplicates ~/Downloads --dry-run
python3 run_app.py history --keyword invoice
python3 run_app.py stats --report summary.md
python3 run_app.py --help
```
Optional install: `pip install -e .` then run `file-organizer ...`.

Custom rules (`--config rules.json`):
```json
{ "Music": [".mp3", ".flac"], "Books": [".epub", ".pdf"] }
```

## Tests
```bash
python3 -m unittest discover tests        # 105 tests, standard library only
```

## Project layout
```
src/file_organizer/
├── web.py / web_page.py  local browser UI + JSON API
├── cli.py            argparse front-end            ├── core_engine.py   scan / dry-run / execute / rollback
├── main.py           interactive menu              ├── transaction.py   write-ahead move journal
├── ui.py             ONLY module that prints       ├── strategies.py    type / date / size strategies
├── validator.py      input validation              ├── duplicates.py    duplicate detection
├── workflows.py      shared use-cases              ├── persistence.py   atomic JSON + CSV audit
├── analytics.py      metrics + report              ├── pathutils.py     pathlib safety helpers
├── config.py         rules, validation, colours    ├── logging_setup.py logging configuration
└── models.py         typed data shapes + status constants
tests/                8 test modules, 105 tests
```
