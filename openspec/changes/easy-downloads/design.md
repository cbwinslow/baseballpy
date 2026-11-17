# Design: easy-downloads

## 1. What the audit found (2026-11-16)
Commands that exist: `ingest` (any source, seasons, datasets, `--option`), `backfill PLAN` and `run PLAN` (plans as TOML or
the built-ins `daily` and `full`; disk guards `--min-free-gb` and `--max-gb`; child processes, retries, resume through
`state/queue.json`), `update` (= `backfill daily`), `status`, `doctor`, `estimate`. Missing: options in a plan stage; a
Python function to download; newest-first order.

## 2. Reuse check
`ingest/backfill.py` (`Stage`, `parse_plan`, `plan_stage`, `run_backfill`), `ingest/runner.py` (`plan_jobs`, `run_jobs`),
`ingest/selection.py` (`parse_seasons`), `get_adapters`, `sync_database`, `shutil.disk_usage` (through the existing
`_disk_usage`). No new dependency. Custom code: the thin Python wrapper (`baseballpy/easy.py`), because the commands hold this
logic inside click functions.

## 3. Evidence (filled in as tasks land)

### 3.1 Evidence (2026-11-16)
Tests written first: `tests/test_backfill_options.py` (10) and `tests/test_python_api.py` (12). The first failed for the
missing keys and module; the old plan tests that assumed oldest-first now say so (`order = "oldest-first"`) because they
test the disk budget. Real dry runs: `baseballpy backfill minors --dry-run` and `bp.backfill("minors", dry_run=True)` both
plan 6 jobs (2021 to 2026) and estimate 28 GB with 48.6 GB free. The scratch scripts of the session (a completion loop, a
minor-league loop with a disk check, a raw clean-up loop) are replaced by `baseballpy backfill minors --min-free-gb 12`, the
automatic completion in `ingest_game_segments` (ADR 143) and `baseballpy convert-raw --apply --remove-old` (a one-time
migration of lakes from before segments; a new user never needs it). Not verified: a real run of the built-in `minors`
plan (the same work is running through `ingest --option sports=all`, which the plan calls).

### 3.2 The seasons override (2026-11-16)
Found: `baseballpy backfill minors-all --dry-run` refused to start on 30 GB free because the whole plan estimated 100 GB.
Added `--seasons` (Gemini wrote it from a brief; reviewed, `mypy --strict`, ruff and 52 backfill and API tests pass) and
corrected the estimates to the measured 3.2 GB per season (`minors` 19 GB for 2021 to now, `minors-all` 61 GB). Real use:
`baseballpy backfill minors-all --seasons 2014-2019 --min-free-gb 10` plans 6 jobs and 19.3 GB with 31.4 GB free, and runs.
