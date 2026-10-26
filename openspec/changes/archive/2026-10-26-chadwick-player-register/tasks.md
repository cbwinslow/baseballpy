# Tasks: Chadwick Player Register & Master Crosswalk

- [x] Implement `src/baseballpy/sources/chadwick/schema.py` defining canonical PyArrow schema
- [x] Implement `src/baseballpy/sources/chadwick/extractor.py` handling GitHub downloads, conditional ETag/commit checks, and caching
- [x] Implement `src/baseballpy/sources/chadwick/normalizer.py` parsing CSV to typed PyArrow Table
- [x] Implement `src/baseballpy/sources/chadwick/register.py` providing `PlayerRecord`, `ChadwickRegister`, and lookup methods
- [x] Expose `bb.chadwick.register()`, `bb.resolve_player()` in `src/baseballpy/__init__.py`
- [x] Write unit tests in `tests/test_chadwick.py` using `tests/fixtures/chadwick/people_sample.csv`
- [x] Verify with `uv run pytest`, `uv run ruff check .`, `uv run mypy src`
- [x] Commit and push to GitHub
