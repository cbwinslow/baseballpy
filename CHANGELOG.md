# Changelog

All notable changes. The version is bumped at release time (see `docs/RELEASING.md` once written); everything below is unreleased.

## Unreleased

### Added
- `v_pitches_unique`: a view with one row per Statcast pitch key; the dataset keeps the provider's repeated 2026 rows (ADR 115, 119).
- `baseballpy run PLAN [--every 6h]`: a Python supervisor that keeps a plan running (child process per stage, retries with backoff, resumes after a restart, no OS scheduler; ADR 90), `baseballpy backfill --stage`, and the queue on the `status` screen.
- Cross-platform behavior (ADR 89): LF line endings for every written text file and in every checkout (`.gitattributes`), `spawn` worker processes, UTF-8 console output, and `tests/test_portability.py` enforcing it.
- The default User-Agent is the one pybaseball sends (`python-requests/2.32.3`), overridable with `BASEBALLPY_USER_AGENT` or `HttpClient(user_agent=...)` (ADR 40).
- `baseballpy backfill PLAN.toml` runs a staged historical backfill (free-space pre-flight, `--max-gb`, `--dry-run`, resume); measured throughput and the plan are in `docs/BACKFILL.md`.
- `catalog status` says why a dataset is not in the lake (`ingest`: `default`, `opt_in`, `on_demand`, `api_only`, with a note) and `--gaps` lists only the MISSING datasets the default ingest should have filled; `catalog show` reports the same.
- One command surface: `baseballpy ingest` (plan, dry-run, bounded concurrency, resume), `catalog list|show|status|audit`, `db sync|views|query|shell`, `stream` (JSONL and idempotent DuckDB upsert), `quarantine list|show`, `audit summary|tail|stats` with `--source/--status/--since`, `doctor`, `docs generate|coverage`, `refs`, `migrate-layout`. Reference: `docs/CLI.md` (generated).
- `baseballpy.ingest`: source-agnostic jobs, selection parser and runner; one `IngestAdapter` per source (ADR 25, ADR 39).
- Complete upstream coverage for Statcast (pitches, minor-league pitches, 34 leaderboard variants), the MLB Stats API (declarative endpoint registry, parameterized stat types, live streamer), Lahman, Chadwick and Retrosheet (every file kind), with strict generated Arrow schemas and `_extras` for drift.
- Column dictionaries with descriptions cited to provider metadata and a coverage ratchet (`docs/columns/`).
- Lake layout v2 (`raw/`, `processed/`, `quarantine/`, `cache/http/`, DuckDB views), `migrate-layout`, pinned upstream refs.
- CI workflows (lint, types, tests with a 90% coverage gate, docs freshness, build) and a weekly upstream audit; `py.typed`.

### Changed
- `teams_season` schema regenerated over every sport/level (the generator now samples per-sport endpoints with all of `ref_sports`, as the ingest fans out): typed `parent_org_id`, `parent_org_name` and `conference_*` columns instead of `_extras`.
- A dotenv file is read only when `BASEBALLPY_ENV_FILE` names one; nothing is picked up implicitly from the working directory.
- MLB fan-out requests tolerate the provider's 404 for sports and teams without data.
- Lint policy now includes bandit (`S`) and complexity ceilings (`PLR0912`, `PLR0915`).
- License is GPL-3.0-or-later (ADR 26).

### Fixed
- `v_game_crosswalk` keeps one row per `game_pk` (the played row of a postponed or rescheduled game) and matches only played MLB games to Retrosheet, so each game and each Retrosheet game appears once (ADR 121).
- The source archive no longer carries local scratch folders and reference dumps (12.1 MB to 2.8 MB).
- A schema migration no longer writes empty `_extras` objects (ADR 118).
- A write lock per dataset and season: a compaction of a season and an ingest of the same season can no longer overwrite each other's chunks (ADR 124).
- A short MLB stat pool, a Retrosheet season built without a missing file and a boxscore taken while the game was live are no longer stored as finished (ADR 125).
- A 429 or 503 pauses every request to that host; the Windows host lock is released explicitly; the audit log records returned errors as failures and keeps its records when a rotation fails (ADR 123).

### Known behaviour
- MLB `/v1/stats` league-wide pools answer HTTP 406 most of the time; the library fills them through `/v1/people?hydrate=stats` and re-fetches them when the route answers again (ADR 53, 117, 120).
- Statcast relabels old pitches after the fact (for example Slider to Sweeper); a closed season is downloaded again only with `--refresh` (docs/sources/statcast.md).
