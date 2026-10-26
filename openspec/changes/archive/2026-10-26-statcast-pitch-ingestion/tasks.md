# Tasks: Statcast Pitch-Level Ingestion Engine

- [x] Create Statcast test fixture in `tests/fixtures/statcast/sample_pitches.csv`
- [x] Implement `src/baseballpy/sources/statcast/schema.py` defining full 90+ column PyArrow schema
- [x] Implement `src/baseballpy/sources/statcast/normalizer.py` conforming to `NormalizerProtocol`
- [x] Implement `src/baseballpy/sources/statcast/extractor.py` with chunking, `aiolimiter`, and caching
- [x] Implement `src/baseballpy/sinks/duckdb.py` conforming to `SinkProtocol`
- [x] Implement `src/baseballpy/sinks/parquet.py` conforming to `SinkProtocol`
- [x] Expose `bb.statcast()`, `bb.to_duckdb()`, `bb.to_parquet()` in `src/baseballpy/__init__.py`
- [x] Add CLI subcommand `baseballpy statcast` in `src/baseballpy/cli.py`
- [x] Write comprehensive unit tests in `tests/test_statcast.py` and `tests/test_sinks.py`
- [x] Run real-world verification and integration test
- [x] Verify test suite with `uv run pytest`, `ruff`, and strict `mypy`
- [x] Commit and push to GitHub
