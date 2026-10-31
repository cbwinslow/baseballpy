# MLB Stats API Ingestion Specification

## Purpose
The MLB Stats API Ingestion Engine extracts, parses, caches, and normalizes official Major League Baseball datasets from `https://statsapi.mlb.com/api` into strongly-typed PyArrow Tables and adaptive multi-target sinks.

---

## 2. Endpoints Covered
The nine hand-written datasets below keep their selected-field schemas; every other endpoint is in the declarative registry (see "Declarative Coverage" at the end), including complete-field twins of these nine.
1. **Schedule & Calendar (`/v1/schedule`):**
   - Game Pk primary numeric keys, scheduled dates, doubleheaders, game type classifications (`R`, `P`, `S`), lifecycle statuses (`S`, `I`, `F`, `D`), home/away teams, and venues.
2. **Official Boxscores (`/v1/game/{game_pk}/boxscore`):**
   - Game-by-game batting and pitching box scores with full individual stat lines.
3. **Standings & Rankings (`/v1/standings`):**
   - Division and wild card standings, wins, losses, winning %, games back, run differential, and streaks.
4. **Teams & Rosters (`/v1/teams`, `/v1/teams/{team_id}/roster`):**
   - Active MLB franchises, minor league circuits, active 26-man and 40-man rosters, and injured list designations.
5. **Transactions (`/v1/transactions`):**
   - Roster moves, options, outright waivers, trades, and injured list transactions.
6. **First-Year Player Draft (`/v1/draft/{year}`):**
   - Draft rounds, picks, players, signing bonuses, and school origins.
7. **Venues (`/v1/venues`):**
   - Ballpark dimensions, capacities, turf types, and roof configurations.

---

## 3. Concurrency, Rate Limiting & Network Pooling
- Host rate limit: 8.0 requests/second, enforced by the shared `HttpClient` (`core/http.py`).
- Persistent connection pooling with HTTP/2 enabled.
- Exponential jitter backoff on transient HTTP failures, by the same client.

---

## 4. Two-Phase Atomic Caching
- Raw JSON (with sha256) is stored under `raw/mlb_api/<dataset>/[season=YYYY/]` and typed Parquet under `processed/mlb_api/<dataset>/[season=YYYY/]` (lake layout v2); each part is written atomically and recorded in the dataset manifest, which drives resume.

---

## Requirements

Declarative coverage (complete-source-coverage, verified live 2026-10-27).

### Requirement: Endpoint Coverage
Every MLB endpoint MUST be a `MlbEndpoint` (path/params template, record path, fan-out scope, key) with a strict schema generated from live responses (`scripts/gen_mlb_schemas.py`). Reference lists, seasons/sports/leagues/divisions/teams, team affiliates/history/coaches/personnel/alumni, rosters of every roster type, players, free agents, jobs, draft prospects, postseason schedules, hydrated schedules, standings of every standings type, league leaders, league-wide player and team stats for every stat type x group that returns data, and per-game linescore, win probability, play-by-play and live-feed plays/pitch events/linescore/officials MUST be ingestible. Routes that do not respond MUST stay registered as `unsupported` with the probe reason; routes that answer 200 with no records MUST be listed as `empty` in `docs/mlb_probe.json`.

#### Scenario: Pitch events of a final game
- **GIVEN** a final `game_pk`
- **WHEN** `game_feed_play_events` is ingested
- **THEN** each event row carries its plate appearance's context plus `pitch_data_*` (speed, coordinates, breaks, spin, zone) and, for batted balls, `hit_data_*`.
- Verified by `tests/test_mlb_stream.py::test_pitch_events_of_a_final_game_carry_pitch_and_hit_data`.

### Requirement: No Field Loss
Nested objects MUST be flattened to dotted keys, arrays kept as JSON text, unknown fields preserved in `_extras` with a one-time drift warning, uncastable cells quarantined, and a payload whose shape contradicts the record path MUST raise.

#### Scenario: Nested objects, arrays and unknown fields are kept
- **WHEN** a payload is flattened and normalized
- **THEN** nested objects become dotted keys, arrays stay JSON text, unknown fields land in `_extras` with one drift warning, bad cells are quarantined, and a payload contradicting the record path raises
- Verified by `tests/test_mlb_coverage.py::test_flatten_dots_nested_objects_and_keeps_arrays_as_json, ::test_unknown_upstream_field_goes_to_extras_and_bad_cells_to_quarantine and ::test_iter_records_carries_wrapper_fields_and_fails_loudly_on_shape_changes`.

### Requirement: Bounded Downloads
Paginated stat requests MUST use `limit`/`offset` pages; a request announcing more than 20,000 rows MUST be refused after its first page unless history ingestion is explicitly allowed (all-time stat types ignore the season: `statsSingleSeason fielding` is 191,958 rows). `ingest_season` MUST skip such endpoints by default.

#### Scenario: Huge result is refused after one page
- **WHEN** a paginated request announces more rows than the limit
- **THEN** it is refused after its first page unless history ingestion is allowed
- Verified by `tests/test_mlb_coverage.py::test_paginated_request_announcing_a_huge_result_is_refused and ::test_paginated_stats_walk_every_page`.

### Requirement: Standings Sentinels
`-` in `gamesBack`/`wildCardGamesBack` is 0 games; `eliminationNumber` `E` is 0 and `-` is NULL; none of these may be quarantined.

#### Scenario: Sentinels are values, not quarantine noise
- **WHEN** standings contain `-` games back or `E` elimination numbers
- **THEN** they become 0 or NULL as specified and nothing is quarantined
- Verified by `tests/test_mlb_coverage.py::test_standings_sentinels_are_values_not_quarantine_noise`.

### Requirement: Live Streaming (implemented)
The streamer MUST implement `StreamExtractorProtocol` (`stream_events(game_pk, ...)`; the constructor does not own a game), poll `feed/live/timestamps` and apply `feed/live/diffPatch` (RFC 6902) to a local copy of the feed, fall back to the full feed when a patch is unavailable or does not reach the announced timestamp, and accept a full feed document where the server answers a wide window with one. It MUST emit `LiveEvent`s keyed `(game_pk, at_bat_index, event_index)` with microsecond UTC timestamps, emit `game_status` events and end cleanly on `Suspended`, `Postponed`, `Cancelled` and `Final`, back off on `Delayed`, persist a watermark so a later stream of the same game emits only new events, retry network failures through `HttpClient` and then raise (never swallow), quarantine undecodable payloads, and map events onto the `game_feed_play_events` schema (`to_arrow`).

#### Scenario: Suspended game
- **WHEN** the game status becomes `Suspended`
- **THEN** a `game_status` event is emitted and the stream ends
- **AND** a later stream for the same `game_pk` emits only events beyond the stored watermark.
- Verified by `tests/test_mlb_stream.py::test_suspended_game_is_emitted_ends_and_resumes_from_the_watermark`.

### Requirement: People, Awards and Incremental Endpoints
Per-person stats (`people_stats_<type>_<group>`), award recipients (a 404 for one award MUST be recorded as an empty part and counted, never retried forever and never hidden), `people_changes`/`game_changes` (append-only `updatedSince` logs) and `people_search` MUST be ingestible through the declarative registry.

#### Scenario: Awards, since and query scopes
- **WHEN** an award has no recipients list, or a `since`/`query` endpoint is built
- **THEN** the award is counted and not refetched, and the endpoint needs its value and is unpartitioned
- Verified by `tests/test_mlb_coverage.py::test_award_without_a_recipients_list_is_counted_and_not_refetched and ::test_since_and_query_scopes_need_their_value_and_are_unpartitioned`.

### Requirement: Completeness
Every stat group listed by `/v1/statGroups`, every sport/level listed by `/v1/sports` (the default of `ingest_season`), every standings type, roster type and game-level resource MUST be ingestible; hand-written datasets that select fields MUST have complete-field twins (`transactions_season`, `draft_picks`, `venues_hydrated`, `game_boxscore_*`). Boxscore players (a dict keyed by player id) MUST be ingested one row per player with their team context. Endpoints for which the generation probe found no records MUST still keep every response as raw JSON, and a later schema generation types them.

#### Scenario: Sports without teams and schema-less endpoints
- **WHEN** a sport has no teams, or an endpoint has no generated schema
- **THEN** the empty sport is counted and not fatal, and the raw JSON is kept
- Verified by `tests/test_mlb_coverage.py::test_sport_without_teams_is_counted_not_fatal and ::test_endpoint_without_generated_schema_keeps_the_raw_json`.

### Requirement: All-Time Stat Pools
All-time stat types ignore the season: `ingest_season` MUST skip them, `ingest_history` MUST fetch them once (stored under the run's season), and any paginated request announcing more than 20,000 rows MUST be refused unless explicitly allowed.

#### Scenario: All-time types are heavy
- **WHEN** the registry is inspected
- **THEN** all-time and league-wide split stat types are `heavy` and season ones are not, so `ingest_season` skips them
- Verified by `tests/test_mlb_coverage.py::test_all_time_stat_types_are_heavy_and_season_ones_are_not and tests/test_mlb_param.py::test_league_wide_situational_splits_are_heavy`.

### Requirement: Half-Inning Ends
The streamer MUST emit a `half_inning_end` event (once) when a completed plate appearance records the third out (AGENTS.md section 5).

#### Scenario: Third out emits one half_inning_end
- **WHEN** a plate appearance records the third out
- **THEN** exactly one `half_inning_end` event is emitted
- Verified by `tests/test_mlb_stream.py::test_third_out_emits_a_half_inning_end_once`.

### Requirement: Provider Lists Are the Registry
Every standings type, roster type and game type listed by the provider MUST be present in the registry (and the `GameType` enum MUST equal `/v1/gameTypes`); `baseballpy catalog audit` MUST report any difference as MISSING or STALE.

#### Scenario: Differences are reported
- **WHEN** the provider lists an item the registry lacks (or the reverse)
- **THEN** `catalog audit` reports MISSING or STALE and exits non-zero; `GameType` and sports match the live reference data
- Verified by `tests/test_audit.py::test_missing_and_stale_items_are_reported_and_fail and tests/test_mlb_coverage.py::test_game_type_and_sport_enums_exist_in_the_live_reference_data`.

### Requirement: Parameterized Stat Types
Every stat type listed by `/v1/statTypes` MUST either have registered stat combinations (including those that need `sitCodes`, `metrics` or an opposing id) or an `unsupported` entry recording the parameters tried and the verification date; `baseballpy catalog audit` MUST report any other stat type. A request the provider answers with HTTP 500 for every subject MUST be listed with its evidence in `PROVIDER_ERRORS` rather than swallowed.

#### Scenario: metric fan-out skips a known provider error
- **WHEN** requests are built for `people_stats_metric_averages_pitching` with metrics `barreledBall` and `launchSpeed`
- **THEN** only `launchSpeed` is requested
- Verified by `tests/test_mlb_param.py::test_metric_the_provider_answers_with_500_is_never_requested`.

### Requirement: Raw Files Record an Upstream Fingerprint
Every raw MLB Stats API payload MUST record an upstream fingerprint in its manifest entry: the provider's ETag when the response carries one, else the sha256 of the payload.

#### Scenario: Fingerprints are recorded
- **WHEN** endpoint payloads are stored
- **THEN** each raw manifest entry holds a fingerprint
- Verified by `tests/test_mlb_coverage.py::test_every_mlb_raw_file_records_an_upstream_fingerprint`.

### Requirement: Stored Tables Follow the Schema
A stored table MUST NOT be served when its recorded schema digest differs from the dataset's current schema (ADR 49); it is fetched again without `--refresh`.

#### Scenario: A schema change refetches
- **WHEN** a stored table's schema digest differs from the dataset's
- **THEN** the next call fetches it again
- Verified by `tests/test_mlb_api.py::test_a_teams_table_written_under_another_schema_is_fetched_again`.

### Requirement: No Hard-Coded Default Season
A function that defaults a season or year MUST default to the current season of the calendar, never to a fixed year, and `refresh=True` MUST reach the network for every dataset.

#### Scenario: Defaults follow the calendar and refresh is honoured
- **WHEN** standings, transactions and the draft are requested without a season, and standings with refresh
- **THEN** the requests carry the calendar's season and refresh fetches again
- Verified by `tests/test_mlb_api.py::test_default_seasons_follow_the_calendar_and_standings_honour_refresh`.

### Requirement: Every Dataset Is Reachable From Python
`baseballpy.sources.mlb_api.table(name, season, **arguments)` MUST return any registered MLB dataset by its registry name, `datasets()` MUST list exactly the registered names, and an unknown name MUST raise an error that lists the valid ones.

#### Scenario: Names resolve
- **WHEN** a hand-written dataset and an unknown name are requested
- **THEN** the table comes back and the unknown name raises
- Verified by `tests/test_mlb_api.py::test_table_reaches_hand_written_and_declarative_datasets_by_name`.

### Requirement: A Refused Request Does Not Stop The Rest
A single-endpoint call MUST raise when the provider refuses a request (HTTP error status). In a season, history or people-stats run (`keep_going`), the other requests MUST still be ingested; the endpoint report MUST list the refusals and the ingest job MUST end with status failed, a detail line and an error naming the first refusals, while the stored data stays.

#### Scenario: A 406 on one game
- **WHEN** one of two game requests answers 406 and the other succeeds
- **THEN** the report has rows and one error, and the job result is failed with the rows of the successful request
- Verified by `tests/test_mlb_coverage.py::test_one_refused_request_does_not_stop_the_others_and_fails_the_job_afterwards`.

### Requirement: League-Wide Pools Survive A Refused Pool Route
When `/v1/stats` answers HTTP 406 for a league-wide player pool whose stat type has a per-person equivalent, the pool MUST be fetched through `/v1/people?personIds=...&hydrate=stats(...)` in batches of the sport's players. Every multi-value parameter in the hydrate expression (`group`, `type`, `sitCodes`, `metrics`) MUST be list-encoded (`sitCodes=[vr,vl]`), because the provider silently keeps only the first value of a comma list inside a hydrate expression; an empty multi-value parameter MUST be omitted. Every provider response MUST be kept as raw bytes, the splits MUST be normalised with the same schema as the direct route, and the pool MUST keep every split code the same request returns on the person route.

#### Scenario: A 406 on the pool route
- **WHEN** the direct route answers 406 and the people route answers 200
- **THEN** the pool's rows are stored and the raw hydrate pages are kept
- Verified by `tests/test_mlb_coverage.py::test_a_refused_league_wide_pool_is_fetched_through_people_hydrate`.

#### Scenario: Two situation codes in one hydrate expression
- **WHEN** a pool request carries `sitCodes=vr,vl`
- **THEN** the hydrate expression carries `sitCodes=[vr,vl]` and both codes are requested
- Verified by `tests/test_mlb_coverage.py::test_hydrate_expression_list_encodes_multi_value_parameters`.

#### Scenario: Every served split code is kept
- **WHEN** the person route returns a split for `vr` and a split for `vl`
- **THEN** the pool stores two rows, one per split code
- Verified by `tests/test_mlb_coverage.py::test_hydrate_fallback_keeps_every_split_code`.

### Requirement: A Probe Reports Provider Health
`baseballpy probe` MUST send one small request to each provider route the project depends on, print the status and time of each, name a fallback where one exists, and exit with code 1 when any route does not answer 200.

#### Scenario: One route is down
- **WHEN** the league-wide pool route answers 406 and the others 200
- **THEN** the table marks that route FAILED with its fallback and the exit code is 1
- Verified by `tests/test_probe.py::test_probe_names_the_failing_route_and_its_fallback` and `tests/test_probe.py::test_probe_passes_when_every_route_answers`.


### Requirement: Split Pools Written Before the Fix Are Rebuilt
A stored `stats_stat_splits_*` part whose parser revision predates the list fix MUST be treated as
stale, so the next run fetches it again without `--refresh`. The revision MUST be derived from the
endpoint's stat type, not from a hard-coded dataset-name list, and every other MLB dataset MUST keep
the stored parts it already has.

#### Scenario: A split pool stored by the old fallback
- **WHEN** a split pool part was written under the earlier revision
- **THEN** the next call fetches it again, while a non-split pool written under the same revision is
  still served from the lake
- Verified by `tests/test_mlb_coverage.py::test_a_split_pool_written_before_the_list_fix_is_fetched_again`.

### Requirement: A Pool Without a Person Equivalent Is Refused
A stat type the person route cannot serve MUST be listed in `NO_PERSON_EQUIVALENT` with its measured
evidence. When `/v1/stats` answers 406 for such a pool, the fallback MUST NOT run and MUST NOT store an
empty part: `PoolFallbackUnavailableError` MUST name the stat type and the evidence, and a `keep_going`
run MUST report the refusal while keeping the data it already stored.

#### Scenario: A single-season pool is refused
- **WHEN** a `statsSingleSeason` pool answers 406 and the person route would answer 200 with no splits
- **THEN** the call raises an error naming `statsSingleSeason` and no empty part is stored
- Verified by `tests/test_mlb_coverage.py::test_a_pool_stat_type_without_a_person_equivalent_is_refused`.

### Requirement: An Oversized Hydrate Batch Shrinks
An HTTP 414 on a hydrate batch MUST halve that batch and retry the same players, down to one id; at one
id the error MUST propagate. Every page that answers 200 MUST be kept as raw bytes with a unique name,
and every player MUST be requested exactly once.

#### Scenario: A batch the provider rejects as too long
- **WHEN** a hydrate batch answers 414
- **THEN** the batch is halved and retried until it fits or one id also fails
- Verified by `tests/test_mlb_coverage.py::test_a_414_on_a_hydrate_batch_halves_it`.

### Requirement: The Probe Exercises the Fallback Shape
`baseballpy probe` MUST send the hydrate request the fallback uses, including a multi-value `sitCodes`
list, so a broken list syntax or an unavailable people route fails the probe before a long run starts.

#### Scenario: The fallback canary is part of the probe
- **WHEN** the probe canaries are built
- **THEN** one canary carries `hydrate=stats(...sitCodes=[vr,vl])` and a 406 on it fails the probe
- Verified by `tests/test_probe.py::test_probe_checks_the_hydrate_list_syntax`.


### Requirement: Every MLB Stats API Download and Ingest Is Audit-Logged and Timed
Every MLB Stats API operation that lists, downloads, parses or stores data MUST write one structured audit event to `logs/audit.jsonl` with the operation name, the source `mlb_api`, the endpoint, the destination, the record count, the duration and whether the answer came from the lake. The operation names MUST be stable and documented: `mlb_api_fetch` and `mlb_api_cache_read` for the hand-written datasets, `mlb_<endpoint>` for a declarative endpoint (including the hydrate pool fallback, whose event records the refused pool URL, and a raw-only endpoint, whose event records the raw files kept), `mlb_snapshot`/`mlb_snapshot_bytes` for a projected read (destination = set name or `complete`) and `mlb_stream` for a live poll. A failed download MUST be logged with status `FAILURE` and the error text and MUST be re-raised.

#### Scenario: A declarative endpoint, cold and cached
- **WHEN** a declarative endpoint is ingested and then ingested again
- **THEN** two `mlb_<endpoint>` events exist, the first with `cache_hit` false and rows, the second with `cache_hit` true
- Verified by `tests/test_mlb_audit.py::test_a_declarative_endpoint_is_audited_cold_and_cached`.

#### Scenario: A raw-only endpoint
- **WHEN** an endpoint without a generated schema is ingested and then ingested again
- **THEN** two `mlb_<endpoint>` events exist, the first with the raw files stored and the second with `cache_hit` true
- Verified by `tests/test_mlb_audit.py::test_a_raw_only_endpoint_is_audited_cold_and_cached`.

#### Scenario: The hydrate pool fallback
- **WHEN** the pool route answers 406 and the people route serves the pool
- **THEN** the `mlb_<endpoint>` event records the stored rows and the refused pool URL as its endpoint
- Verified by `tests/test_mlb_audit.py::test_the_pool_fallback_records_its_rows_and_refused_url`.

#### Scenario: A projected snapshot
- **WHEN** `snapshot(fields="score")` and `snapshot_bytes()` run
- **THEN** `mlb_snapshot` and `mlb_snapshot_bytes` events exist with destinations `score` and `complete`
- Verified by `tests/test_mlb_audit.py::test_a_projected_snapshot_is_audited_with_its_set_name`.

#### Scenario: A finished stream
- **WHEN** a stream of a final game ends
- **THEN** its `mlb_stream` event records every event it emitted, the game status event included
- Verified by `tests/test_mlb_audit.py::test_a_finished_stream_is_audited_with_its_event_count`.

#### Scenario: A refused download
- **WHEN** a request answers 406
- **THEN** the endpoint's audit event has status `FAILURE` and carries the HTTP error, and the error propagates
- Verified by `tests/test_mlb_audit.py::test_a_refused_request_is_logged_as_a_failure`.
