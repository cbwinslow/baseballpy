# Tasks: lake-inventory-columns

Order: 1.1 -> 1.2 -> 1.3 -> 1.4.

- [x] 1.1 Tests first in `tests/test_database.py`: `test_season_catalog_is_the_lake_inventory` (new columns:
  `view_name` equals the registry view, `bytes` equals the sum of the Parquet file sizes,
  `last_written_at` is a timestamp, an unpartitioned dataset has a NULL season, an unregistered folder
  gets `<source>_<dataset>`). It fails before the change.
  Done when the test fails for the missing columns.
- [x] 1.2 `database.py`: `_season_catalog_rows` returns bytes and newest mtime; `_create_season_catalog`
  adds `view_name`, `bytes`, `last_written_at` (empty-lake form too).
  Done when 1.1 passes and the older `test_season_catalog_and_crosswalk_views` still passes unchanged.
- [x] 1.3 Docs and records: README and `docs/DATA_WORKFLOW.md` name the view as the inventory with an
  example query; ADR 98; spec requirement in `lake-access`; evidence in `design.md`.
  Done when `docs generate --check` and `openspec validate --specs` pass.
- [x] 1.4 Gates and live check: pytest, ruff check, ruff format --check, mypy --strict, then
  `baseballpy db sync` on the real lake and the inventory queried for Statcast, Retrosheet and MLB.
  Done when output is pasted in `design.md` and the change is archived.
