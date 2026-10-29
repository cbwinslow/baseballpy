# Design: dlt as the extract-normalize-load core

## Spike result (2026-10-29; `scripts/dlt_spike.py`, 5 live requests, one at a time, same bytes through both paths)

| Case | Our flatten path | dlt (raw records, schema_contract evolve) |
|---|---|---|
| `teams_season` | 30 rows, 34 columns | 30 rows, 34 columns, no child tables |
| `schedule_hydrated` (2024-07-04) | 15 rows, 247 columns (nested lists as columns) | 15 rows, 238 columns + 4 child tables (`broadcasts` 94 rows, `broadcasts__free_game_types` 2, `linescore__innings` 137, `officials` 60) |
| `people_stats_season_hitting` (3 players) | 2 rows, 52 columns | 2 rows, 49 columns |

Compared with our strict schemas (`MLB_SCHEMAS`) after mapping dlt's `__` to our `_`:
- Every column dlt produced also exists in our schema (0 only-in-dlt). Types agree (string/double/bool) except integers: our `int32`, dlt `BIGINT` (a widening; harmless but not identical).
- Only-in-ours: `_extras`; columns other samples contributed (`conference_*`, `parent_org_*`); **parent context our flattener carries**: `dates_*` in the schedule (part of its key `dates.date`) and `stats_type_display_name`/`stats_group_display_name`/`stats_exemptions` in the player stats; nested lists we keep as columns (`broadcasts`, `officials`, `linescore_innings`) which dlt turns into child tables with parent keys.
- The filesystem (Parquet) destination logged "Falling back to `append`" for `merge` on all three: merge needs a SQL destination (DuckDB) or our own dedup.
- Wall-clock (0.001-0.006 s ours vs 2-9 s dlt) is not comparable: ours is the in-memory flatten only, dlt's includes pipeline setup, normalize and two loads (DuckDB and Parquet).
- Not tested here: type stability across several loads (dlt's variant columns), league-wide `v1/stats` (blocked, B-30), Statcast and Retrosheet.

## Reading
dlt reproduces our column set from raw JSON with no hand-written flattening, no `_extras` and no generated schema, and its child tables are the relational form of what we keep as nested columns. What it does not do on its own: keep the parent context (needs a map step or `include_from_parent`), keep our narrower integer types and strict schema (needs `columns=` hints from the generated schemas), merge on Parquet, keep raw bytes with sha256, quarantine uncastable cells, or rate-limit.

## Decision path
ADR 42 adopts dlt for the load/normalize stage of the MLB API first, behind `IngestAdapter` (tasks 3.1-3.2), keeping our `HttpClient` (rate limits, User-Agent), raw store and quarantine. Statcast and Retrosheet are separate follow-up changes if the MLB migration holds.
