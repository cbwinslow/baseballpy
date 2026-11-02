# Design: mlb-schema-drift-regeneration

## 1. The defect, with evidence

The split-pool schemas were generated from the direct `/v1/stats` payload before 2026-10-29. A hydrate
`stats(...)` split object carries more fields. Measured on the first stored page of
`stats_stat_splits_hitting` (2025, sport 1, 150 players, 9,421 splits):

| Field | Rows carrying it |
|---|---|
| `season`, `stat`, `player`, `sport`, `gameType`, `split` | 9,421 (all) |
| `position` | 9,301 |
| `team`, `league` | 8,895 |
| `opponent` | 1,418 |
| `numTeams` | 526 |

`gameType` (all rows), `sport.abbreviation` (all rows) and `numTeams` (multi-team players) are absent
from `MLB_COLUMNS` for the ten split pools; the normalizer logs a `schema_drift` warning and keeps them
in `_extras`. The old generator cannot fix this by itself: the direct route answers 406, `get_json`
returns `None`, and the endpoint is recorded `empty`.

## 2. The generation fallback

`scripts/gen_mlb_schemas.py` already reuses runtime helpers for requests (`requests_for`) instead of
hand-building URLs. The fallback does the same:

1. `profile()` asks the request's own path as today.
2. If the answer is `None` **and** the endpoint is a pool (`.paginated` and path
   `MLB_POOL_PATH`), it calls `hydrate_sample()`:
   - player ids from `v1/sports/{sport}/players?season={season}` (the same enumeration the runtime
     fallback uses),
   - `POOL_BATCH` ids per request, `HYDRATE_SAMPLE_BATCHES` (2) batches, through
     `hydrate_request_params()` (the new public helper both sides share),
   - each answer unwrapped with `stats_payload()` into the `stats[].splits` shape `iter_records()`
     already understands.
3. The probe entry gains `"route": "direct"` or `"route": "hydrate"` and `"fallback_pages"`, so the
   evidence says how the sample was obtained. `PROVIDER_ERRORS` still records the 406.

Sampling two batches per context is enough for schema discovery (the fields are structural and repeat
across players); it does not replace the full live ingest, which stays the runtime's job.

## 3. Invalidation of old parts

No parser revision bump is needed and none is added. `core/stores.py::spec_fingerprint` hashes the
schema fingerprint into every stored chunk's `schema_sha256`, so widening a schema makes every part
written under the old one stale and it is rebuilt on the next ingest (checked in
`tests/test_stores.py`; the split pools' revision 2 stays as the ADR 55 marker).

## 4. Anti-drift test

`tests/test_mlb_coverage.py` gains `test_every_fixture_key_has_a_typed_column`: for every endpoint with a
schema, flatten its committed fixture and assert every `snake()` key is a column of the generated schema.
A field kept only in `_extras` now fails the suite; before regeneration the split-pool fixtures were cut
from the direct payload, so this check could not see the drift — from now on the fixtures carry the
hydrate keys.

## 5. As built

- `scripts/gen_mlb_schemas.py`:
  - When the direct `MLB_POOL_PATH` request returns 406, `profile()` falls back to `hydrate_sample()` (2 batches of `POOL_BATCH` players across seasons 2024 and 2015).
  - Pre-flight fix: `profile()` only attempts `DEEP_PAGE_OFFSETS` when the direct request was successful (`direct_ok`), preventing dozens of doomed HTTP 406 requests.
  - `sample_contexts()` excludes `MLB_POOL_PATH` from the 20-sport fan-out since situational split stats are structural across levels and MLB (sport 1) discovers all fields.
- `endpoints.py`: `KEY_OVERRIDES` overrides `stats_stat_splits_advanced_pitching` key to `("season",)` because `rank` was only present in the legacy direct route and is absent in hydrate payloads.
- Regeneration: all 10 `stats_stat_splits_*` datasets regenerated in `mlb_tables.py`, fixtures and `docs/mlb_probe.json` (`route: "hydrate"`, `fallback_pages: 2`, `game_type`, `num_teams`, `sport_abbreviation` typed).
- Anti-drift test: `tests/test_mlb_coverage.py::test_every_fixture_key_has_a_typed_column` passes for all covered endpoints.
