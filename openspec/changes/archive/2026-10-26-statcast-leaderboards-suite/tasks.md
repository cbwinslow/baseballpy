# Tasks: Statcast Full Leaderboards & Metrics Suite

- [x] 1. Update `docs/sources/statcast.md` with exhaustive documentation of all 11 leaderboard endpoints, query parameters, and column dictionaries.
- [x] 2. Implement typed PyArrow schemas for all leaderboard endpoints in `src/baseballpy/sources/statcast/leaderboards.py`.
- [x] 3. Implement `StatcastLeaderboardExtractor` and `StatcastLeaderboardNormalizer` in `src/baseballpy/sources/statcast/leaderboards.py`.
- [x] 4. Expose public functions in `src/baseballpy/sources/statcast/__init__.py`.
- [x] 5. Author unit tests in `tests/test_statcast.py` with mock fixtures verifying extraction, normalization, and typing.
- [x] 6. Run `uv run pytest`, `uv run ruff check .`, and `uv run mypy src` to verify 100% green compliance.
- [x] 7. Update `openspec/specs/statcast-ingestion/spec.md` and archive the change to `openspec/changes/archive/`.
