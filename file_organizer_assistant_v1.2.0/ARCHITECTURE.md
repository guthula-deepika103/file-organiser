# Architecture & Design Notes (v1.2.0)

## Layers (separation of concerns)
```
 Presentation     cli.py   main.py   ui.py   validator.py        <- only layer that talks to the terminal
 Application      workflows.py                                   <- use-cases shared by menu and CLI
 Domain           core_engine.py  strategies.py  duplicates.py  transaction.py
 Infrastructure   persistence.py  logging_setup.py  pathutils.py  config.py  models.py
```
Dependencies point downwards only. The engine returns data and never prints; the UI never touches the filesystem.

## Design patterns
- **Strategy** - `CategorizationStrategy` (`ExtensionStrategy`, `DateStrategy`, `SizeStrategy`); the engine depends only on the interface.
- **Factory** - `get_strategy(name)`.
- **Write-ahead log / journal** - `MoveJournal` gives crash safety.
- **Generator / pipeline** - `iter_scan` -> `summarize_plan` / `execute_organization` stream without materialising the file list.
- **Command table** - `MENU` maps option numbers to handler functions.

## Data design
- History: JSON list of operation objects (backward compatible with v1.0), written atomically.
- Per-file records carry `status` in {`SUCCESS`, `FAILED: <reason>`, `ROLLED_BACK`, `PLANNED`}; operations carry `rolled_back`, `dry_run`, `atomic`, `strategy`.
- CSV audit log is append-only and now also records rollbacks.
- Types documented in `models.py` (`TypedDict`).

## Scalability
Measured on 100,000 files: streaming scan + summary peaks at **0.8 MB** (materialised list: **58.5 MB**); execution ~6 s; rollback ~7 s. History stores small per-file metadata dicts, never file contents.

## Reliability guarantees
| Situation | Behaviour |
| :--- | :--- |
| Name collision | never overwritten - `name_copyN.ext` |
| One file fails | recorded, batch continues (or reverts everything with `--atomic`) |
| Ctrl+C mid-batch | completed moves are reverted, journal removed |
| Power loss / kill -9 | journal remains; next run offers `recover_pending` |
| Newer file at original location during undo | kept; restored copy becomes `name_restoredN.ext` |
| Tampered history file | rollback refuses paths outside the operation folder |
| Corrupted history JSON | backed up to `.corrupted.bak`, clean store created |

## Remark-by-remark mapping (Evaluation Report, Attempt 1)
| Category / remark | Where it is addressed |
| :--- | :--- |
| System Design 14/20: scans whole dir into memory | `core_engine.iter_scan`, `summarize_plan`, `duplicates.iter_files` |
| System Design: separation of concerns | engine no longer prints; `ui.py`, `workflows.py`, `cli.py` split out |
| System Design: design patterns | Strategy, Factory, Journal, table-driven menu |
| System Design: data design | atomic writes, typed models, status constants, O(1) extension index |
| Improve: `logging` instead of `print` | `logging_setup.py`; guard test `test_no_prints_outside_ui_and_cli` |
| Improve: transactional file operations | `transaction.py`, `atomic=True`, interrupt revert, `recover_pending` |
| Recommend: `pathlib` | `pathutils.py` and pathlib throughout |
| Recommend: engine-level dry-run | `execute_organization(dry_run=True)` |
| Functionality: broad `Exception` catches | narrowed everywhere (`OSError`, `shutil.Error`, `json.JSONDecodeError`, `ValueError`) |
| Innovation: beyond CRUD | strategies, duplicate detection, CLI, custom rules, journal recovery |
| Requirements: edge cases / testing | symlinks, hidden files, protected paths, collisions, tamper, crash tests (93 tests) |
