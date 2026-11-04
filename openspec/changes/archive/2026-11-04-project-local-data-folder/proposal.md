# Project-local data folder

## Why
The owner wants the downloaded data kept inside the project folder, in a dot folder named `.baseballpy`, so everything stays close and tidy.

## What changes
- With no setting, the data folder is `.baseballpy/` in the nearest project folder (a folder with `pyproject.toml` or `.git`) above the working directory; outside any project it stays `~/.baseballpy/`.
- `BASEBALLPY_HOME` and `BASEBALLPY_CACHE_DIR` still win.
- `.baseballpy/` is in `.gitignore`.
- Range decision (owner, 2026-11-04): Lahman, Chadwick and Retrosheet are backfilled for all history; Statcast and the MLB API from 2008 to the current year (clock-driven).
