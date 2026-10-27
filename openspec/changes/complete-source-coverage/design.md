# Design: Complete Source Coverage

The authoritative list of endpoints/datasets, parameters, keys and partitioning is
`docs/ENDPOINT_CATALOG.md` (written alongside this change). This document defines the machinery.

## 1. Schema generation and the `_extras` rule (C-2, C-5, C-6, C-9)
- `scripts/gen_schemas.py <source> <dataset> [--sample file]` fetches a representative payload (live, or a recorded fixture), flattens it, and prints a Python `pa.schema([...])` with proposed types and per-column nullability. Type proposal uses Arrow inference over the full sample, then conservative narrowing (`int64 -> int32/int16` only when range-checked on the full historical sample; `float64 -> float32` only for tracking metrics, never for money/rates needing precision such as batting average or ERA stored as decimal strings upstream).
- Schemas live next to each source (`schema.py`) and are committed. The generator is a dev tool, not a runtime dependency.
- Runtime normalization (`normalize_records(records, spec)`):
  1. Flatten nested JSON by path join with `_` (`pitchData.coordinates.pX` -> `pitch_data_coordinates_p_x` by an explicit `snake()` function, collisions raise at spec-load time).
  2. For each schema column take the mapped value; coerce with `checked_cast` (quarantine failures).
  3. Collect keys not in the spec; if any, serialize them to JSON in `_extras` (type `string`, nullable) and log `schema_drift` once per (dataset, field) per process; also append to `quarantine`-adjacent `drift/<source>/<dataset>.jsonl` for later promotion into the schema.
- Flat CSV sources use header-based mapping (`map_by_header`), with unknown columns appended as typed-by-inference-or-string columns named by `snake(header)`.
- Contract tests per dataset: (a) fixture payload -> table equals golden Parquet schema; (b) payload with an extra field -> field appears in `_extras`; (c) payload missing a field -> NULL; (d) Hypothesis: arbitrary string/NaN/None in any column never raises.

## 2. MLB Stats API framework (C-1, C-2)
```python
@dataclass(frozen=True)
class MlbEndpoint:
    dataset: str  # registry name, e.g. "people_stats_season"
    path: str  # "/v1/people/{personId}/stats"
    version: str = "v1"  # "v1.1" for game feed
    params: Mapping[str, str]  # fixed params, e.g. {"stats": "season", "group": "hitting"}
    fan_out: (
        FanOut | None
    )  # how to iterate: per season, per team, per person, per game_pk, per date window
    root: str  # JSON path of the record list, e.g. "dates[].games[]"
    parent_fields: Mapping[
        str, str
    ]  # fields hoisted from ancestors, e.g. {"game_date": "dates[].date"}
    spec: DatasetSpec
    freshness: CachePolicy
    hydrate: str | None  # value for ?hydrate= (schedule, teams, people, venues support it)
```
- `MlbApiExtractor.fetch(endpoint, **path_params)` -> raw JSON bytes (stored in `raw/mlb_api/<dataset>/...`), via `HttpClient`.
- `MlbApiNormalizer.normalize(endpoint, payload)` walks `root`, hoists parent fields, flattens, applies spec.
- Fan-out strategies (all bounded by `max_concurrency`): `per_season` (seasons from `/v1/seasons/all`), `per_team` (from `/v1/teams?sportId=...&season=Y`), `per_person` (from `people_all` / rosters), `per_game` (from schedule `game_pk` with `status.abstractGameState in {Final}`), `per_date_window` (schedule windows ≤ 31 days).
- Hydration: schedule, teams, people, venues and standings are fetched with a maximal `hydrate` list (documented per dataset) to capture linescore, decisions, probable pitchers, team records, venue fields, officials etc. in one call; the flattened tables keep all hydrated fields; list-valued hydrations become child tables (e.g. `schedule_game_officials`, `schedule_probable_pitchers`).
- **Game feed tables** from `GET /api/v1.1/game/{game_pk}/feed/live` (final games, historical): `game_feed_meta`, `game_feed_plays` (one row per at-bat: result, about, count, matchup incl. splits, rbi, scoring flags, `play_id`), `game_feed_play_events` (one row per event incl. pitches: `details`, `count`, `pitchData` {startSpeed, endSpeed, strikeZoneTop/Bottom, strikeZoneWidth/Depth, coordinates (aX,aY,aZ,pfxX,pfxZ,pX,pZ,vX0,vY0,vZ0,x,y,x0,y0,z0), breaks (breakAngle, breakLength, breakY, breakVertical, breakVerticalInduced, breakHorizontal, spinRate, spinDirection), zone, typeConfidence, plateTime, extension}, `hitData` {launchSpeed, launchAngle, totalDistance, trajectory, hardness, location, coordinates}, `pitchNumber`, `playId`, `startTime`, `endTime`, `isPitch`, `type`), `game_feed_runners` (movement, details, credits), `game_feed_linescore_innings`, `game_feed_boxscore_players` (all stat groups: batting/pitching/fielding/game status, season stats, positions, flags), `game_feed_boxscore_teams`, `game_feed_officials`, `game_feed_game_info`, `game_feed_weather_venue`, `game_feed_decisions`, `game_feed_scoring_plays`, `game_feed_pitch_sequence`.
- Separate documented endpoints when richer or lighter: `game_linescore`, `game_boxscore`, `game_play_by_play`, `game_win_probability`, `game_context_metrics`, `game_content`, `game_color`, `game_changes` (incremental sync).
- Generic `GET /v1/{meta}` lookups (game types, stat types, stat groups, positions, roster types, standings types, pitch types, event types, hit trajectories, situation codes, schedule event types, sky/wind, languages, platforms, review reasons, logical events, metrics, league leader types, jobs, awards, sports, leagues, divisions, conferences) are ingested as small reference datasets `mlb_ref_<name>` so enums are data-driven; the hand-written `GameType`/`GameState`/`SportId` enums are validated against them by a test.
- ID/season discovery order for `ingest --all`: seasons -> sports -> leagues/divisions -> teams per season -> people (via `/v1/sports/{id}/players?season=Y` per sport/season) -> schedules per season/sport -> per-game feeds -> stats/leaders/awards/draft/transactions/attendance per season.

## 3. Live streamer (C-3)
- Source of truth for efficient polling: `GET /api/v1.1/game/{pk}/feed/live/timestamps` (list of change timestamps) and `.../feed/live/diffPatch?startTimecode=<ts>&endTimecode=<ts>` (JSON patch) with fallback to full `feed/live?timecode=` and ETag/`metaData.timeStamp` comparison. If diffPatch is unavailable, full-feed polling compares `metaData.timeStamp` before parsing (AGENTS §5.2).
- Event model `LiveEvent` (msgspec Struct, frozen): `game_pk, at_bat_index, event_index, play_id, event_kind` (`pitch|pickoff|stolen_base|substitution|action|half_inning_end|play_result|game_status`), pitch fields incl. full `pitchData`/`hitData`/`breaks`, count, batter/pitcher/fielder ids, `play_result`, `ts_utc` (µs) and `received_utc`.
- Status lifecycle: handle `Preview/Pre-Game/Warmup` (wait; bounded by `max_inactivity_minutes`), `Live/In Progress` (poll), `Delayed` (back off to 30 s), `Suspended` (emit `game_status`, end stream, record resume info), `Postponed`/`Cancelled` (emit and end), `Final`/`Game Over` (flush and end), doubleheader aware via `game_pk`.
- Errors: transient network errors go through `HttpClient` retry; after retries are exhausted, emit a `stream_error` audit event and re-raise (never `except Exception: pass`). Malformed play payloads go to quarantine and the stream continues.
- Idempotent sink contract: events carry key `(game_pk, at_bat_index, event_index)`; `to_arrow(events)` maps to `game_feed_play_events`-compatible schema so live and historical data share a table and can be upserted.
- Implements `StreamExtractorProtocol` (`stream_events(game_pk, ...)`) exactly; the class constructor no longer owns `game_pk`.

## 4. Statcast / Savant (C-4, C-5)
### Pitch search
- Endpoint `GET https://baseballsavant.mlb.com/statcast_search/csv` with params `all=true`, `type=details`, `game_date_gt/lt`, `hfSea` (season), `hfGT` (game types, pipe-delimited and URL-encoded), `player_type`, `sport_id` (minor leagues where available), `hfTeam`, `min_pitches`, etc. All documented filters are passed through `StatcastQuery` (typed, validated) and recorded in the manifest chunk key.
- Schema: regenerate from the live CSV header across eras (2008 PITCHf/x-era, 2015 Statcast, 2020, 2023 pitch-clock, 2024 bat-tracking, 2025) — union of all columns is the schema; era-specific columns are nullable. Unknown columns -> extra columns (header-based).
- Row cap: window bisection (harden H-9). `ingest_season(year)` iterates 5-day windows from first to last schedule date of that season discovered from the MLB schedule (spring training and postseason included per `game_types`), `ingest_all(start_year=2008)`.
- Idempotency key `(game_pk, at_bat_number, pitch_number)`; processed layout `processed/statcast/pitches/season=YYYY/part-<window>.parquet`.
### Game feed
- `GET https://baseballsavant.mlb.com/gf?game_pk={pk}` JSON (exit velocity/xBA per batted ball, pitch tracking, lineup) as dataset `statcast.game_feed_*` (documented, probed live; marked unsupported if blocked).
### Leaderboards (replace heuristic normalizer)
- Registry `LEADERBOARDS: dict[str, LeaderboardSpec]` where spec = `slug`, `route`, `params` (typed: `type`, `min`, `year`, `startYear/endYear`, `position`, `team`, ...), `granularity` (player-season, player-pitchtype, team-season, game, rolling), `schema` (explicit), `keys`, `min_year`. Catalog in `docs/ENDPOINT_CATALOG.md` §Savant.
- Normalizer: header-based; explicit types from schema; unknown columns preserved; `%` stripped only where the schema says percent; sentinel values (`""`, `--`, `null`) -> NULL; never guess from column names. Remove `_safe_int` truncation (`int(float(v))`).
- Fetch all years from `min_year`, all `type` variants (batter/pitcher/fielder/catcher/...), with `min=0`-style "no qualifier" where supported so *all* players are captured (documented per leaderboard).
- Custom leaderboard (`/leaderboard/custom?...&selections=...`) support for arbitrary metric selections is exposed as `statcast.custom_leaderboard(selections, year, type)`.

## 5. Lahman (C-6)
- Sources are ONLY: (1) the owner's repo `cbwinslow/lahman-database-csv` (`data/<Table>.csv`, pinned SHA, full 1871–2025 release); (2) a user-supplied zip/directory via `import_archive`. `chadwickbureau/baseballdatabank` MUST NOT be used anywhere (its data stops around 2023): a test greps `src/` and `docs/` to enforce this. The remote repo/ref is configurable (`BASEBALLPY_LAHMAN_REPO`, `BASEBALLPY_LAHMAN_REF`) so users can point at their own fork; there is no automatic fallback to any other repository — on 404/5xx after retries the error is raised with a hint to use `import_archive`. The manifest records the source (`remote@sha` or `local-import`) of each table. The loader also validates the latest `yearID` in `Batting`/`Teams` (must be ≥ the last completed MLB season minus 1) and warns loudly if the data looks stale.
- 27 strict schemas generated from the real headers (tables enumerated in catalog); `_extras` for unknown columns; PK documented per table; row counts validated against manifest (+ sanity assertion that `People.playerID` is unique and every `Batting.playerID` exists in `People`, reported as data-quality warnings, not errors).
- Dual-mode import (zip/dir) retained but writes `raw/` atomically and processes via the same normalizer.

## 6. Retrosheet (C-7)
- Discovery: `GET https://api.github.com/repos/chadwickbureau/retrosheet/git/trees/<ref>?recursive=1` (via `HttpClient`, `GITHUB_TOKEN` optional) cached for 24 h; the file list drives: available seasons, event files per season (regular `.EVA/.EVN`, postseason/all-star `.EVE`), roster files, game logs (regular and postseason), box-score files, schedule files, and every file under `reference/` and `misc/`. No hard-coded filenames except dataset-to-pattern rules in the registry.
- Datasets (registry): `event_files`, `events`, `events_postseason`, `boxscore_batting`, `boxscore_pitching`, `box_files` + parsed `box_*` (if the format is parseable by chadwickpy; otherwise raw-only with documented reason), `daily_splits`, `substitutions`, `rosters`, `gamelogs`, `gamelogs_postseason`, `schedule`, and one `reference_<stem>` dataset per CSV in `reference/` (generic header-based reference parser; known ones keep explicit schemas).
- Downloader: `HttpClient` with bounded concurrency (default 4), per-file sha256 recorded, 404 recorded as `ABSENT` (not COMPLETED); a season is COMPLETED only if every file listed by the tree for that season is present and valid; `ingest_all(start, end)` skips completed seasons and resumes via manifest.
- Parsing from raw is offline and CPU-bound: process pool (`concurrent.futures.ProcessPoolExecutor`, bounded) per season file; results streamed to Parquet via `pq.ParquetWriter` in row-group batches (no full-season Python-dict lists).
- GPL boundary: `chadwickpy` imports isolated in `sources/retrosheet/_chadwick_adapter.py`; raises a clear `ImportError` naming the `retrosheet` extra if absent (see hygiene change for the license decision).

## 7. Chadwick Register (C-8)
- Discover shard/auxiliary file list from the tree (`data/people-*.csv`, `data/names.csv`, `data/links.csv` if present; the probe records which exist). Revalidate against the pinned/latest SHA every 24 h (conditional compare of SHA, not blind cache hit). Header-based schema + `_extras`; datasets `register` (people), `register_names`, `register_links` (when present).

## 8. Generated docs (C-9)
`baseballpy docs generate` renders for every `DatasetSpec`: endpoint (URL template, method, params, headers), freshness policy, partitioning, keys, row-cap/rate-limit notes, and a column dictionary table (`column | arrow type | nullable | upstream path/name | description | sentinel/quirks`). Descriptions come from a hand-curated `docs/columns/<source>.yaml` (merged; missing description fails the docs test for explicitly-mapped columns). Output replaces content between `<!-- BEGIN GENERATED:<dataset> -->` / `<!-- END GENERATED:<dataset> -->` markers in `docs/sources/<source>.md`; a test regenerates into a temp dir and fails on diff.

## 9. Test strategy
- Recorded fixtures (`tests/fixtures/<source>/<dataset>/*.{json,csv}`, small, sanitized) per dataset; respx-mocked end-to-end tests for each fan-out strategy; no real network in unit tests (AGENTS §9.4).
- Live probe suite `tests/live/` (marked `@pytest.mark.live`, excluded by default, run manually) that hits each catalog endpoint once with tiny inputs and asserts non-empty + schema-compatible; its results regenerate the "verified on" column in the catalog.
- Hypothesis for normalizers; golden-schema tests; registry completeness test (every catalog row has a spec, a doc section, a fixture).
