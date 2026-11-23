# File Organizer Assistant - User Manual (v1.2.0)

## 1. Overview
Sorts cluttered folders into sub-folders safely: every batch can be previewed, undone, and survives crashes. Use the interactive menu (`python3 run_app.py`) or the CLI (`python3 run_app.py --help`).

Files created next to where you run the tool: `organizer_history.json`, `organizer_audit.csv`, `organizer.log` (change with `--data-dir`). These files are never organized.

---

## 2. Menu options

| # | Option | Notes |
| :-: | :--- | :--- |
| 1 | Organize Target Directory | choose grouping `type` / `date` / `size`; preview first; optional all-or-nothing mode |
| 2 | Rollback / Undo | lists the last 5 operations that still have restorable files |
| 3 | Query & Search Records | keyword and category filters |
| 4 | Analytics & Summary Export | writes `organizer_executive_summary.md` |
| 5 | Automated Demo | recreates `demo_unorganized_workspace`, shows preview + engine dry-run, organizes it atomically |
| 6 | Find & Quarantine Duplicates | byte-identical files; oldest copy stays, others go to `Duplicates/` (undo-able) |
| 7 | Exit | |

### Safety behaviour
- **Preview before action**; nothing moves without `y`.
- **Collisions** never overwrite: `report.pdf` -> `report_copy1.pdf`.
- **All-or-nothing mode** (`--atomic` / answer `y` in the menu): if any file fails, everything already moved is put back.
- **Ctrl+C** during a batch reverts the files already moved.
- **Crash recovery**: if a previous run died mid-batch, the next run in that folder offers to restore the partially moved files.
- **Undo** never overwrites a newer file: it is restored as `name_restored1.ext`. Undoing twice is harmless.
- Sub-folders, symlinks and hidden files are skipped; system folders (`/`, `/etc`, `C:\Windows`, ...) are refused.

---

## 2b. Browser interface
Run `python3 run_app.py web` (or double-click `start_web.bat`). Your browser opens http://127.0.0.1:5000 . Enter a folder path, optionally tick *Include subfolders* / *All-or-nothing*, press **Generate preview**, review the table, press **Organize these files**. Every operation appears under **Recent operations** with an **Undo** button. **Find duplicates** and **Download report** are on the same page. The server only accepts connections from your own computer and uses a per-run security token. Stop it with Ctrl+C.

## 3. Command line

```bash
python3 run_app.py organize PATH [--strategy type|date|size] [--config rules.json]
                                 [--dry-run] [--atomic] [--include-hidden] [--yes]
python3 run_app.py undo [--id OP-XXXXXXXX] [--yes]
python3 run_app.py history [--keyword K] [--category C] [--limit N]
python3 run_app.py stats [--report FILE]
python3 run_app.py duplicates PATH [--no-recursive] [--dry-run] [--atomic] [--yes]
# global: --data-dir DIR   -v/--verbose   --version
```
Exit codes: `0` ok, `1` failure, `2` usage error, `130` interrupted.

### Custom rules file
```json
{ "Music": [".mp3", ".flac"], "Books": [".epub", ".pdf"] }
```
Category names must be plain folder names; an extension may belong to only one category.

---

## 4. Suggested 3-minute demo
1. `python3 run_app.py` -> option **1**, type `/non_existent_path` -> validation message, no crash.
2. Option **5** -> preview table, engine dry-run, atomic organize, report.
3. Option **2** -> undo the demo; files return to the original folder.
4. Option **6** on the demo folder -> duplicate `System_Logs_2026_backup.txt` detected.
5. Exit (**7**), relaunch, option **4** -> history persisted.
6. Show `python3 run_app.py organize <folder> --dry-run` and `python3 -m unittest discover tests`.
