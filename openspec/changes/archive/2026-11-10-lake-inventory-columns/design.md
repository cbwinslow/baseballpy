# Design: lake-inventory-columns

## Reuse check (docs/agents/TOOLING.md)

1. Row: "Local analytics, views, SQL" -> `duckdb` views only; `core/sql.py` for quoting.
2. The view and its row source already exist (`BaseballDatabase._season_catalog_rows`,
   `_create_season_catalog`); the files come from `core.listing.visible_parquet`.
3. No custom helper needed: `Path.stat()` gives size and mtime during the walk that already opens each
   footer.
4. The dataset-to-view name comes from the registry (`DATASETS`), never a hard-coded list.

## Decisions

- Extend the existing view instead of adding a second one: one place to look, no duplicate rows.
- `last_written_at` from file mtime: cheap and honest about what it is. Manifest `fetched_at` would need
  every manifest parsed (some are several MB; MLB has hundreds), which `db sync` should not pay.
- Columns are appended so `SELECT dataset, season, row_count` keeps working (existing test).

## Evidence

- Test first: `tests/test_database.py::test_season_catalog_is_the_lake_inventory` failed for the missing
  columns, then passed; the older `test_season_catalog_and_crosswalk_views` passes unchanged.
- Gates (2026-11-10): `pytest` 1619 passed, 6 skipped; `ruff check`, `ruff format --check`,
  `mypy --strict src` clean; `docs generate --check` up to date; `openspec validate --specs` 22 passed.
- Real lake (`db sync`, then a read-only query): columns `source, dataset, season, row_count, files,
  view_name, bytes, last_written_at`; per source (datasets, season rows, rows, GB): retrosheet 25 / 2012 /
  50,087,183 / 1.16; statcast 38 / 429 / 19,817,552 / 2.06; mlb_api 140 / 2034 / 61,797,233 / 31.57;
  statcast pitches 2025 = 868,045 rows, view `statcast_pitches`, 103,609,225 bytes.
