# Tasks: Two-Phase Atomic Ingestion Gates & Retrosheet Engine

- [x] Implement `src/baseballpy/core/atomic.py`: `AtomicWriter` and `ManifestTracker`
- [x] Upgrade `StatcastExtractor` to use `AtomicWriter` and `ManifestTracker`
- [x] Implement `src/baseballpy/sources/retrosheet/schema.py`: Canonical PyArrow schemas for game logs, rosters, and event files
- [x] Implement `src/baseballpy/sources/retrosheet/downloader.py`: Fastly GitHub CDN mirror extractor with atomic raw file caching
- [x] Implement `src/baseballpy/sources/retrosheet/parser.py`: Pure in-memory transformation using `chadwickpy`
- [x] Implement `src/baseballpy/sources/retrosheet/api.py`: Retrosheet facade (`events()`, `game_logs()`, `rosters()`)
- [x] Expose `baseballpy.retrosheet` in `src/baseballpy/__init__.py`
- [x] Write unit tests in `tests/test_atomic.py` and `tests/test_retrosheet.py`
- [x] Verify test suite with `uv run pytest`, `uv run ruff check .`, `uv run mypy src`
- [x] Commit and push to GitHub
