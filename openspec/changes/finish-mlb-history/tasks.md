# Tasks

- [x] 1.1 games-only job: `include_season`, `games_only`, test (ADR 91)
- [x] 1.2 `baseballpy run --compact`: compaction after each finished stage, test
- [x] 1.3 `plans/mlb-games-history.toml`: 16 stages, newest first, dry run checked
- [ ] 2.1 run the plan with `baseballpy run plans/mlb-games-history.toml --every 24h` and record the time and compacted size per season in design.md
- [x] 2.2 verify coverage: for every season 2008 to 2026, every finished major-league game has rows in every per-game dataset (cancelled games excepted) and record the table in design.md
- [x] 2.3 final `baseballpy compact` and `baseballpy catalog layout` with no MIXED_SCHEMA; `read("award_recipients")` returns slugs for all rows (closes B-306)
- [x] 2.4 `baseballpy catalog audit` against the providers (needs no download running) with no MISSING, REVIVED or ERROR finding
- [x] 3.1 the five default datasets still missing (`standings_first_half`, `standings_second_half`, `stats_season_advanced_catching`, `stats_season_advanced_fielding`, `stats_season_advanced_game`): fixed, or marked with a note and probe evidence
- [x] 3.2 type the rare fields still in `_extras` (reschedule fields, draft `xrefIds`, affiliate conference, roster `parentTeamId` and `note`) by sampling rows that carry them
- [x] 3.3 open the change `batched-chunk-writes`: fewer files and manifest writes per game (the profile in this change's design)
- [x] 3.4 live end-to-end test of `baseballpy stream` on a real game and a replay of a stored game through it (own change if it needs code)
- [ ] 4.1 v1 release steps of `docs/RELEASING.md`: changelog, version, `uv build`, `twine check`, TestPyPI in a clean environment (the owner decides the tag)
  - Evidence 2026-11-14 (all but the owner's steps): `uv build` gives the sdist and wheel (0.1.0), `twine check` passes for both, `mkdocs build --strict` passes, last weekly `live` audit succeeded; the wheel installed in a clean Python 3.12 venv outside the repo (`doctor`: 510 datasets, 9 adapters), `ingest chadwick` into an empty home, `verify-roundtrip` clean, and the register table has the same count and hash as the main lake. Left for the owner: version number, changelog date, TestPyPI upload (needs the owner's account), tag.
- [x] 4.2 add macOS to the CI matrix and fix what it finds
- [x] 4.3 review the open Dependabot alerts and give the crosswalk tests fixtures (B-311)
- [x] 3.5 open the change `shared-raw-bytes`: each upstream response is stored once. `raw/mlb_api` is 23.3 GB and holds the live feed four times (3.02 GB each) and the boxscore six times (0.57 GB each), about 12 GB of copies (measured 2026-11-08)

- [ ] 5.1 review round 1 follow-ups (ADR 123): (a) DONE (ADR 124): ingest and compaction write lock, loud read of a vanished chunk; DONE (ADR 131) the manifest lock is an OS lock, no stale break; (b) DONE (ADR 125) MLB paging: an empty page before the announced total is an error; (c) DONE (ADR 125) Retrosheet season fingerprint only over files that exist; (d) DONE (ADR 125) boxscore status read before the fetch, postponed is not final; (e) DONE (ADR 126) an empty player list is not remembered and its empty pool is provisional; (f) `segrebuild._newest_by_url` without Python objects (ADR 114); (g) DONE (ADR 126) `old_compact` removed; (h) DONE (ADR 126) Retrosheet parsers quarantine under their real dataset names; (i) DONE (ADR 126) Polars and dlt sinks write audit records; rejected with evidence (ADR 126): retries for `download_sync`; (j) DONE (ADR 130): rebuilt on the real lake (5,475 chunks, 0 stale left, compacted, `verify-roundtrip` clean on 5 stat pools), still open: (f) `segrebuild._newest_by_url` memory
- [x] 5.2 JSON cell-by-cell round-trip for the MLB API datasets (`verify-roundtrip` skips 365 of them today): re-read the raw JSON (loose files and response-log segments), recompute the loader's flattened values with the same code, compare each with the stored cell, report every loss (built by Opus 5.5 in its own worktree, reviewed by Claude)
