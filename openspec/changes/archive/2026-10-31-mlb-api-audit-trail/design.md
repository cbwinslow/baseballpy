# Design: mlb-api-audit-trail

## 1. Call-site audit of every MLB Stats API path that reaches the network

Every HTTP call site in `sources/mlb_api/` is inside a `default_audit_logger.track(...)` block; the
table records the enclosing tracked operation and what the tracker receives. Verified by reading each
call site on 2026-10-31.

| Call site | Function | Audit operation | Records set |
|---|---|---|---|
| `extractor.py:61` `http.get_sync` | `MlbApiExtractor._fetch` | `mlb_api_fetch` | `len(content)` bytes, `cache_hit=False` |
| `extractor.py:77` `pq.read_table` | `MlbApiExtractor._read_cached` | `mlb_api_cache_read` | rows, `cache_hit=True` |
| `generic.py:506` `http.get_sync` | `_ingest_raw_only` | `mlb_<endpoint>` | raw files stored (was untracked; see 4) |
| `generic.py:289` `http.get_sync` | `_pool_player_ids` (inside `fetch_request`) | `mlb_<endpoint>` | rows of the typed table |
| `generic.py:322` `http.get_sync` | `_pool_pages_by_hydrate` (inside `fetch_request`) | `mlb_<endpoint>` | rows of the typed table |
| `generic.py:372/384` `http.get_sync` | `_get_paginated` (inside `fetch_request`) | `mlb_<endpoint>` | rows of the typed table |
| `generic.py` cached branch | `fetch_request` | `mlb_<endpoint>` | rows, `cache_hit=True` |
| `stream.py:587` | `_snapshot` | `mlb_snapshot` / `mlb_snapshot_bytes` | 1, destination = set name / `complete` |
| `stream.py:657/661` | `stream_live_events` polling | `mlb_stream` | emitted events, status |

Above these, `baseballpy ingest` records one `ingest` event per job in `ingest/runner.py`, and the
Retrosheet source has the same two levels (`retrosheet_download_file` per file,
`retrosheet_ingest_season` per run).

## 2. What the test asserts

`tests/test_mlb_audit.py`, one test per path, all with `respx` and the isolated `BASEBALLPY_HOME` of
`conftest.py`:

1. **Declarative endpoint, cold and cache hit** — `MlbEndpointExtractor.ingest` on a fixture endpoint:
   two `mlb_<endpoint>` events, first `cache_hit=False` with `records > 0`, second `cache_hit=True`, both
   with the endpoint URL and a destination path under `processed/`.
2. **Raw-only endpoint, cold and cache hit** — `standings_postseason` (no generated schema): two
   `mlb_<endpoint>` events around one HTTP call, records = raw files kept, destination under `raw/`.
3. **Hydrate pool fallback** — `/v1/stats` 406, people 200: one `mlb_<endpoint>` event whose records
   equal the stored rows, endpoint is the pool URL (the request that was refused), status `SUCCESS`.
4. **Projected snapshot** — `GamedayLiveStreamer.snapshot(..., fields="score")` and `snapshot_bytes`:
   `mlb_snapshot` with destination `score`, `mlb_snapshot_bytes` with destination `complete`, one record
   each.
5. **Stream** — the existing `mlb_stream` FAILURE assertion stays in
   `test_sources_hardening.py`; this module adds the success case's `mlb_stream` event with the emitted
   count.
6. **A refused request** — a 406 on one game endpoint produces a `mlb_<endpoint>` event with status
   `FAILURE` and the HTTP error text, so a failed download is visible in `baseballpy audit tail`.

## 3. Docs

`docs/sources/mlb_api.md` gains a "Telemetry" section with the operation table above (names, what they
record, the reader commands). `docs/CLI.md` already documents `baseballpy audit summary|tail|stats`; no
change there.

## 4. As built

Two defects were found by writing the tests; both are fixed here, before the tests assert the behaviour.

1. **`_ingest_raw_only` was untracked.** The three endpoints without a generated schema
   (`people_stats_metric_log_hitting`, `people_stats_metric_averages_hitting`, `standings_postseason`)
   downloaded raw JSON with no audit event. The loop now runs inside one `mlb_<endpoint>` event
   (`endpoint` = the route, `destination` = the raw directory, records = files stored or already
   cached, `cache_hit` only when the run stored nothing).
2. **`mlb_stream` under-counted.** The tracker was updated after each pitch, but the `game_status`
   event that ends a stream was yielded without `tracker.set_records(...)`, so the audit row was short
   by one for every finished game. The count is now set after that event too.

Everything else in 1 held. The docs section is in `docs/sources/mlb_api.md` ("Telemetry"), and the
requirement is merged into `openspec/specs/mlb-api-ingestion/spec.md`.
