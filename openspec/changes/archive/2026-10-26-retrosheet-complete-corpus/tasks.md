# Tasks: Retrosheet Complete Corpus & Chadwick Suite Ingestion

- [x] 1. Update `docs/sources/retrosheet.md` with exhaustive documentation of all endpoints, parameters, tables, and column dictionaries.
- [x] 2. Expand `RetrosheetExtractor` in `src/baseballpy/sources/retrosheet/extractor.py` to extract postseason archives, postseason game logs, and reference tables (`ballparks`, `teams`, `ejections`, `coaches`, `relatives`, `biofile`).
- [x] 3. Define typed PyArrow schemas for box scores, daily splits, substitutions, comments, and reference tables in `src/baseballpy/sources/retrosheet/schemas.py`.
- [x] 4. Expand `RetrosheetNormalizer` in `src/baseballpy/sources/retrosheet/normalizer.py` to normalize box scores, daily splits, substitutions, comments, and reference tables.
- [x] 5. Implement top-level facade functions under `src/baseballpy/sources/retrosheet/__init__.py`.
- [x] 6. Author comprehensive unit tests in `tests/test_retrosheet.py` with mock fixtures verifying extraction, normalization, and typing.
- [x] 7. Run `uv run pytest`, `uv run ruff check .`, and `uv run mypy src` to verify 100% green compliance.
- [x] 8. Update `openspec/specs/retrosheet-ingestion/spec.md` and archive the change to `openspec/changes/archive/`.
