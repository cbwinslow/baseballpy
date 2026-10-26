# Change Proposal: Two-Phase Atomic Ingestion Gates & Retrosheet Engine

## Why
1. Ingestion pipelines spanning multi-season queries (Statcast, Retrosheet, Lahman) are vulnerable to network dropouts and interruptions. Writing directly to target files risks corrupting partial files, causing missing data or duplicate records upon restart.
2. An atomic two-phase write pattern (`.part` ➔ atomic `os.replace()`) combined with a lightweight `manifest.json` checkpoint enables instantaneous pause, resume, and zero duplicate downloads.
3. Retrosheet historical play-by-play, game logs, and rosters need to be absorbed into `baseballpy.sources.retrosheet` using `chadwickpy>=0.4.0` in memory, strictly following our two-tier raw/processed cache layout (`raw/` and `processed/`) and our strongly-typed PyArrow schema rules.

## What Changes
1. Implement `baseballpy.core.atomic`:
   - `AtomicWriter`: Context manager streaming writes to `{filename}.part` and executing atomic rename only after format validation.
   - `ManifestTracker`: Thread-safe JSON manifest tracking chunk statuses (`COMPLETED`, `IN_PROGRESS`, `FAILED`), ETags, and record counts for pause/resume.
2. Upgrade `StatcastExtractor` to route all chunk downloads through `AtomicWriter` and `ManifestTracker`.
3. Implement `baseballpy.sources.retrosheet`:
   - `schema.py`: Canonical PyArrow schemas for Retrosheet Game Logs (161 columns), Rosters, and Chadwick Event records.
   - `downloader.py`: Fastly GitHub CDN mirror extractor using `AtomicWriter` to download and cache season files to `raw/{year}/`.
   - `parser.py`: Pure in-memory transformation using `chadwickpy` to parse event files, game logs, and rosters directly into typed PyArrow Tables in `processed/`.
4. Expose top-level API:
   - `baseballpy.retrosheet.events(...)`
   - `baseballpy.retrosheet.game_logs(...)`
   - `baseballpy.retrosheet.rosters(...)`
5. Comprehensive unit tests and integration tests in `tests/test_atomic.py` and `tests/test_retrosheet.py`.
