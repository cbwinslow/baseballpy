# Change Proposal: Complete Source Coverage — Ingest Every Table Every Endpoint Offers

## Context & Motivation
Goal: `baseballpy` must be able to download, normalize, store and document **all** data offered by
Statcast/Baseball Savant, the MLB Stats API, Lahman, Chadwick and Retrosheet. The review found it covers
a small fraction (IDs `C-n`). AGENTS §3 forbids dropping upstream fields; AGENTS §1.4 requires every
endpoint and every column to be documented.

## Findings Fixed
| ID | Gap |
|----|-----|
| C-1 | MLB Stats API: 8 of ~100 endpoints (schedule, boxscore, standings, teams, roster, transactions, draft, venues). Missing people/stats/leaders/awards/game feed (historical)/linescore/play-by-play/win probability/umpires/etc. |
| C-2 | MLB schemas are narrow (boxscore 17 batting columns, schedule 16 columns, live events omit `hitData` and spin/break). Fields are dropped, violating AGENTS §3.1. |
| C-3 | Streamer omits exit velocity/launch angle/distance/spin/break/zone/play result; never reads `metaData.timeStamp` or the diffPatch/timestamps endpoints; no status lifecycle handling (delay/suspend/postpone). |
| C-4 | Savant leaderboards: types guessed by column-name substrings (`bats` -> NULL, `average_*` -> int, `pa` -> string); 12 routes vs ~35 real leaderboards; enum/route mismatch; no schemas. |
| C-5 | Statcast pitch search: schema is a snapshot (95 cols) without header-based drift handling (see harden H-10), no game-type filter, no per-season/all-seasons ingest, no Savant game-feed (`/gf`), no minor-league (`sport_id`) option. |
| C-6 | Lahman: only 8 of 27 tables have strict schemas; unknown columns dropped; non-canonical fork as the sole source. |
| C-7 | Retrosheet: only event files, game logs, rosters and six reference CSVs; no box-score files, schedules, other `reference/` files, or tree discovery; downloads are serial; no all-seasons helper; postseason handled by a hard-coded filename list. |
| C-8 | Chadwick: register shards only; names/links unverified; unauthenticated GitHub API; cache never revalidates against upstream SHA. |
| C-9 | No machine-readable catalog; docs are hand-written and drift from code (e.g. "94 columns" vs 95; "11 leaderboards" vs 12). |

## Guiding Rules (apply to every dataset)
1. **Nothing is dropped.** Every normalizer maps known fields to typed columns and stores any unmapped fields in a trailing `_extras` column (JSON string) — or as extra typed string columns for flat CSV sources — and logs each newly discovered field once per run.
2. **Raw is always kept** in `raw/` (JSON/CSV as received) so a schema fix never needs a re-download (`reprocess`).
3. **Explicit schemas.** No type guessing from names. Schemas are generated from real upstream headers/payloads by `scripts/gen_schemas.py`, reviewed, committed, and covered by fixture tests.
4. **Discovery over hard-coding.** Seasons, files and endpoint metadata (game types, stat types, positions, sports, leagues) are discovered from upstream (`/seasons/all`, GitHub tree API, `/statTypes`, ...) and cached.
5. **Every dataset is registered** in `DATASETS` (see restructure change) and automatically gets: a view, a doc page section with endpoint + column dictionary (generated), a CLI `ingest` target, and a conformance test.
6. **Endpoint reality check.** Each endpoint in `docs/ENDPOINT_CATALOG.md` is probed live once (`scripts/probe_endpoints.py`); the result (HTTP status, sample size, date) is recorded; endpoints that 404/403 are marked `unsupported` with evidence instead of silently omitted.

## Proposed Changes
1. `core/datasets.py` registry populated for all sources (≈120 datasets; see catalog).
2. MLB Stats API: generic endpoint framework (`MlbEndpoint` spec + one flattening normalizer with typed column maps) replacing per-endpoint copy-paste; ≈60 datasets; per-season and per-game ingest; historical game feed ingest (`game_feed_*` tables: plays, play_events, pitches, hit_data, runners, credits, linescore innings, boxscore players, officials, weather, venue details); broad schemas that keep all fields.
3. Streamer rewrite: full event content, `metaData.timeStamp`/`diffPatch` efficient polling, status lifecycle, `StreamingConfig` honored, quarantine on bad payloads, microsecond UTC timestamps.
4. Savant: header-based pitch normalizer with live-generated schema (all columns), `game_types`, `sport_id`, `player_type`; per-season/all-seasons ingest with truncation bisect; leaderboard registry (≈35 leaderboards) with explicit schemas; `/gf` game feed dataset; park factors and percentile ranks.
5. Lahman: 27 strict schemas from real headers; sourced only from the owner's `cbwinslow/lahman-database-csv` (pinned ref, configurable repo) or user-supplied data via `import_archive` (never `chadwickbureau/baseballdatabank`, whose data stops around 2023), with a staleness warning; `_extras` for unknown columns.
6. Retrosheet: GitHub tree discovery; datasets for event files (regular/postseason/all-star), box-score files, schedules, rosters, game logs (regular/postseason), every CSV in `reference/` (generic reference parser keyed by header), plus parsed tables (events, boxscores, daily splits, substitutions); bounded-concurrency downloader; `ingest_all`.
7. Chadwick: discover shards and auxiliary files via tree; revalidate against pinned/latest SHA; schema from header + `_extras`.
8. Generated docs: `baseballpy docs generate` writes the column-dictionary tables into `docs/sources/*.md` between marker comments; CI test fails if docs are stale.

## Out of Scope
Third-party sources in `docs/ROADMAP.md` (FanGraphs, Baseball-Reference, MiLB-specific scrapers, NPB/KBO, Hawkeye biomechanics) — remain roadmap items.

## Impact
New public API per dataset (`baseballpy.mlb.people(...)`, `baseballpy.statcast.leaderboard("percentile-rankings", ...)`, etc.) and `baseballpy ingest <source> [--all]` (CLI in `unified-pipeline-and-cli`). Existing function names remain. Recorded in ADR 24.

## As built (2026-10-27)
- All five sources are implemented and verified live (see `tasks.md` section 7 and the probes `docs/endpoint_probe.json`, `docs/savant_probe.json`, `docs/mlb_probe.json`).
- The scope grew where review against the owner's no-data-left-behind rule found gaps (ADR 30): every provider-listed stat group, every sport/level, complete-field twins of hand-written MLB datasets, boxscore players, per-person stats, award recipients, incremental `changes` logs, raw-only fallback for schema-less endpoints, the all-time stat pools (`ingest_history`), the Savant game feed (on demand and per season), and two more Savant leaderboards whose rows are embedded in the page (`fielding_run_value`, `rolling`).
- Documented non-goals that remain (each with evidence): Retrosheet `.EB*` box accounts are raw only (format spec unreachable); minor-league Statcast pitches are not reachable through `statcast_search` (`sportId`/`hfLevel` ignored or empty); `catch_probability` has no usable upstream rows; column descriptions in the generated docs are not yet written (`docs/columns/<source>.yaml`).
