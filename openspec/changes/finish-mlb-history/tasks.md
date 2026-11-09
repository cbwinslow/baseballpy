# Tasks

- [x] 1.1 games-only job: `include_season`, `games_only`, test (ADR 91)
- [x] 1.2 `baseballpy run --compact`: compaction after each finished stage, test
- [x] 1.3 `plans/mlb-games-history.toml`: 16 stages, newest first, dry run checked
- [ ] 2.1 run the plan with `baseballpy run plans/mlb-games-history.toml --every 24h` and record the time and compacted size per season in design.md
- [ ] 2.2 verify coverage: for every season 2008 to 2026, every finished major-league game has rows in every per-game dataset (cancelled games excepted) and record the table in design.md
- [ ] 2.3 final `baseballpy compact` and `baseballpy catalog layout` with no MIXED_SCHEMA; `read("award_recipients")` returns slugs for all rows (closes B-306)
- [ ] 2.4 `baseballpy catalog audit` against the providers (needs no download running) with no MISSING, REVIVED or ERROR finding
- [x] 3.1 the five default datasets still missing (`standings_first_half`, `standings_second_half`, `stats_season_advanced_catching`, `stats_season_advanced_fielding`, `stats_season_advanced_game`): fixed, or marked with a note and probe evidence
- [ ] 3.2 type the rare fields still in `_extras` (reschedule fields, draft `xrefIds`, affiliate conference, roster `parentTeamId` and `note`) by sampling rows that carry them
- [x] 3.3 open the change `batched-chunk-writes`: fewer files and manifest writes per game (the profile in this change's design)
- [x] 3.4 live end-to-end test of `baseballpy stream` on a real game and a replay of a stored game through it (own change if it needs code)
- [ ] 4.1 v1 release steps of `docs/RELEASING.md`: changelog, version, `uv build`, `twine check`, TestPyPI in a clean environment (the owner decides the tag)
- [x] 4.2 add macOS to the CI matrix and fix what it finds
- [x] 4.3 review the open Dependabot alerts and give the crosswalk tests fixtures (B-311)
- [x] 3.5 open the change `shared-raw-bytes`: each upstream response is stored once. `raw/mlb_api` is 23.3 GB and holds the live feed four times (3.02 GB each) and the boxscore six times (0.57 GB each), about 12 GB of copies (measured 2026-11-08)

