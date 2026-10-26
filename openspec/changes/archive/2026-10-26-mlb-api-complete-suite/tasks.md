# Tasks: MLB Stats API Complete Suite & Real-Time Streaming

- [x] 1. Update `docs/sources/mlb_api.md` with exhaustive documentation of all endpoints, parameters, tables, and column dictionaries.
- [x] 2. Implement typed PyArrow schemas in `src/baseballpy/sources/mlb_api/schemas.py`.
- [x] 3. Define high-speed `msgspec.Struct` decoding models in `src/baseballpy/sources/mlb_api/models.py`.
- [x] 4. Implement `GamedayLiveStreamer` in `src/baseballpy/sources/mlb_api/stream.py` with monotonic sequence diffing and ETag caching.
- [x] 5. Implement `MlbApiExtractor` and `MlbApiNormalizer` in `src/baseballpy/sources/mlb_api/extractor.py` and `normalizer.py`.
- [x] 6. Implement public facade in `src/baseballpy/sources/mlb_api/api.py` and `__init__.py`.
- [x] 7. Implement `PolarsSink` and `DltSink` in `src/baseballpy/sinks/`.
- [x] 8. Update top-level `src/baseballpy/__init__.py`.
- [x] 9. Author comprehensive unit tests in `tests/test_mlb_api.py` and `tests/test_sinks.py`.
- [x] 10. Run `uv run pytest`, `uv run ruff check .`, and `uv run mypy src` to verify 100% green compliance.
- [x] 11. Update `openspec/specs/mlb-api-ingestion/spec.md`, `real-time-streaming/spec.md`, and `multi-target-sinks/spec.md` and archive the change.
