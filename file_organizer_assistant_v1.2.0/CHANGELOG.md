# Changelog

## 1.2.0 (web interface + all v1.1.0 changes)
### Web interface
- `python3 run_app.py web` / `start_web.bat`: browser UI (preview, organize, undo, duplicates, analytics, report download) on the standard library only.
- Security: loopback only, Host check, per-run token, body size limit, CSP, no innerHTML.
- `--recursive` / "Include subfolders" scanning; already-organized files are skipped so re-runs are harmless.
### Added
- Engine-level `dry_run` for `execute_organization` (nothing created, moved or journaled; collisions predicted).
- Generator-based `iter_scan()` + streaming `summarize_plan()`; `scan_directory()` kept as sorted-list wrapper.
- Transactional execution: write-ahead journal (`transaction.py`), `atomic=True` mode, automatic revert on Ctrl+C, `recover_pending()` after a crash.
- `strategies.py` (type / date / size) and custom JSON category rule files with validation.
- `duplicates.py`: SHA-256 duplicate finder, quarantine into `Duplicates/` with undo.
- `cli.py`: `organize`, `undo`, `history`, `stats`, `duplicates` sub-commands (`--dry-run`, `--yes`, `--atomic`, `--strategy`, `--config`, `--data-dir`, `-v`).
- `logging_setup.py`: rotating `organizer.log`; `-v` mirrors DEBUG to stderr.
- `ui.py` (single presentation module), `workflows.py` (shared use-cases), `pathutils.py`, `models.py`.
- Per-file `ROLLED_BACK` status, rollback audit rows in CSV, `rolled_back` flag on operations.
- Protected-folder guard (`/`, `/etc`, `C:\Windows`, ...), symlink and hidden-file skipping, app state files never organized.
- 93 unit tests (was 8) including failure injection, crash recovery and tamper tests.

### Changed
- All diagnostics use `logging`; `print` only in `ui.py`.
- `pathlib` for path handling; specific exception types instead of `except Exception`.
- Engine no longer renders UI (`display_preview_table` moved to `ui.py`).
- History is written atomically (temp file + fsync + replace).
- Menu is table-driven (handler functions) instead of one long if/elif; Exit is now option 7, duplicates is option 6.
- Demo mode is repeatable (marker-protected reset) and includes a duplicate file.

### Fixed
- `.sh` was mapped to two categories (second mapping unreachable).
- Rollback could silently overwrite a newer file with the same name; now restores as `name_restoredN`.
- Rollback of an already-rolled-back operation produced misleading "missing file" errors.
- Closed stdin (EOF) caused an infinite prompt loop.
- Analytics: percentage denominator included failed files; `os.sys.platform` hack; crash on missing timestamp.
- Organizer could move its own history / log files when run on its working folder.
- CSV audit log cells starting with `= + - @` are now neutralised (formula injection).
