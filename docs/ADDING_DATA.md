# Adding data: the naming rule and how to add a dataset or a source

Every table has one name, and that name is the folder, the registry key and the DuckDB view:

```
processed/<source>/<dataset>/...      folder   e.g. processed/lahman/awards_share_managers/
lahman.awards_share_managers          registry key  (<source>.<dataset>)
lahman_awards_share_managers          DuckDB view   (<source>_<dataset>; MLB views start with mlb_)
```

## The naming rule

- Lower-case words joined by single underscores (`awards_share_managers`, `game_feed_plays`).
- The view is the source name plus the folder name. The one exception is the MLB API, whose views start with `mlb_` (`mlb_game_feed_plays`) while its source is `mlb_api`.
- The provider's own spelling is kept only where we talk to the provider (file names, download addresses, git trees, column names). For Lahman, `AwardsShareManagers` is the file `AwardsShareManagers.csv`; the table is `awards_share_managers`.
- `tests/test_table_names.py` fails when a new dataset breaks the rule, so you cannot forget it.
- The names in the owner's PostgreSQL `raw` schema (for example `lahman_awards_share_managers`) are the model for the style; they are a style guide, not a requirement (models read the Parquet files directly).

## Add a dataset to an existing source

| Source | What to do |
| :--- | :--- |
| MLB API | Add one `MlbEndpoint` to `sources/mlb_api/endpoints.py`, run `uv run python scripts/gen_mlb_schemas.py --only <name>`, add a fixture and a test. |
| Statcast leaderboard | Add one `LeaderboardDef` to `sources/statcast/lb_catalog.py`, run `uv run python scripts/gen_savant_schemas.py --only <name>`, add a test. |
| Lahman table | Add the member to `LahmanTable` (`sources/lahman/schema.py`; the member name is the underscore name in capitals) and regenerate the schemas with `uv run python scripts/gen_schemas.py lahman <dir-with-csvs>`. Lahman's own spelling is found by matching the generated table list. |
| Retrosheet, Chadwick | Add the dataset in the source's `api.py` and register it in `sources/catalog.py`. |

Then run the gates (`CLAUDE.md`), `uv run baseballpy docs generate` and `uv run python scripts/master_coverage_audit.py`.

## Add a whole new source

1. Add the source name to `SOURCES` in `core/datasets.py`.
2. Write an adapter in `sources/<source>/adapter.py` that follows `IngestAdapter` (`plan(selection)` returns jobs, `run(job)` runs one) and register its factory with `register_adapter` in `sources/adapters.py`. Sources reach the rest of the code only through this adapter (`tests/test_ingest_contract.py`, `tests/test_architecture.py`).
3. Register every dataset (schema, partition, keys, view, doc anchor) in `sources/catalog.py::register_all()`.
4. Write `docs/sources/<source>.md`, add a host rate to `RateLimitConfig` if it is a new host (`core/config.py`), and add an OpenSpec change, an ADR and tests.

Keep everything the provider offers (typed columns or `_extras`); if something cannot be ingested it stays registered as `unsupported` with probe evidence.
