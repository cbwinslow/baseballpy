# AI Agent Bulletin Board & Coordination Center

This board coordinates parallel and multi-session AI agents (Claude Code, Gemini/Antigravity, Cursor, etc.) working on `baseballpy`.

---

## Operating Rules for All Agents

1. **Read First:** Before touching or modifying any files, read `## Active Checkouts` below.
2. **Never Clobber:** If a file or task is listed under `Active Checkouts`, DO NOT modify, overwrite, or delete those files. Pick an unassigned task from `docs/agents/BACKLOG.md` instead.
3. **Create Task If Missing:** If no task exists in `docs/agents/BACKLOG.md` or on the board for the work you need to perform, open an OpenSpec change (or task entry), add the task row to `BACKLOG.md`, and claim it here first. Never begin unmapped work.
4. **Claim Before Coding:** When starting a task, claim your lock with `uv run baseballpy agent claim <task_id> [--agent <name>] [--files <paths>] [--note <status>]` (which records the checkout on this board and appends a `TASK_CLAIMED` event to `docs/agents/agent_log.jsonl`).
5. **Log on Completion:** When your slice or task is finished:
   - Release the lock with `uv run baseballpy agent release <task_id> "<summary>"` (which moves the entry to `Recent Completed Handoffs` and logs `TASK_COMPLETED`).
   - Update `docs/agents/BACKLOG.md` and run `uv run python scripts/project_map.py`.

---

## Active Checkouts (Locked — Do Not Disturb)

---

## Recent Completed Handoffs

- **2026-11-11 20:31 UTC [blain]:**
  - **Tasks:** `B-397`.
  - **Summary:** compact-one-writer 1.1-1.4: per-dataset compaction lock (ADR 99); repair tasks 2.2-2.4 stay open

- **2026-11-11 01:48 UTC [blain]:**
  - **Tasks:** `B-393`.
  - **Summary:** v_season_catalog is the lake inventory: view_name, bytes, last_written_at; ADR 98; change archived

- **2026-11-09 03:25 UTC [blain]:**
  - **Tasks:** `B-392`.
  - **Summary:** read_part retries when a refresh moves the chunk it is reading

- **2026-11-09 01:28 UTC [blain]:**
  - **Tasks:** `B-369`.
  - **Summary:** views/read/ProcessedStore list season=*/*.parquet, hide _open/_legacy/.part; migration never rewrites segment files

- **2026-11-09 01:14 UTC [blain]:**
  - **Tasks:** `B-368`.
  - **Summary:** game_segments.py: URL groups from the registry, one decode, ingest_game_segments; opt-in --option storage=segments

- **2026-11-09 00:52 UTC [blain]:**
  - **Tasks:** `B-367`.
  - **Summary:** tests first for the MLB switch (4) and the view listing (2); all fail as expected

- **2026-11-09 00:35 UTC [blain]:**
  - **Tasks:** `B-366`.
  - **Summary:** lineage column kept out of the registered schema digest; scan_dataset reads old parts and segment files together

- **2026-11-09 00:24 UTC [blain]:**
  - **Tasks:** `B-365`.
  - **Summary:** cache check verifies segment files and every raw row's hash

- **2026-11-09 00:13 UTC [blain]:**
  - **Tasks:** `B-364`.
  - **Summary:** one writer per source and season through the host lock; all seven segment tests pass

- **2026-11-09 00:00 UTC [blain]:**
  - **Tasks:** `B-363`.
  - **Summary:** refresh of a committed segment under the same names; raw keeps old rows; stopped refresh finished on start

- **2026-11-08 23:49 UTC [blain]:**
  - **Tasks:** `B-362`.
  - **Summary:** segment commit: renames, commit line, start-up cleanup and journal replay; 5 of 7 segment tests pass

- **2026-11-08 22:53 UTC [blain]:**
  - **Tasks:** `B-361`.
  - **Summary:** ProcessedSegmentFiles (50-unit row groups, _raw_sha256, .part in _open) and SegmentWriter skeleton built

- **2026-11-08 22:43 UTC [blain]:**
  - **Tasks:** `B-360`.
  - **Summary:** seven segment tests written first; fail as expected (module missing)

- **2026-11-08 22:34 UTC [blain]:**
  - **Tasks:** `B-359`.
  - **Summary:** measured zstd levels, page and row-group size, row order on 250 real 2024 games; design section 3 updated

- **2026-11-08 22:21 UTC [blain]:**
  - **Tasks:** `B-358`.
  - **Summary:** raw segment writer + commit line + read built; response log tests pass (16)

- **2026-11-08 21:59 UTC [blain]:**
  - **Tasks:** `B-357`.
  - **Summary:** journal writer/reader built in core/responselog.py; 8 journal tests pass; 4 log tests await B-358

- **2026-11-08 21:49 UTC [blain]:**
  - **Tasks:** `B-356`.
  - **Summary:** four response-log tests written first; fail as expected (module missing)

- **2026-11-08 21:46 UTC [blain]:**
  - **Tasks:** `B-355`.
  - **Summary:** cause found: same URL fetched on different days; recorded in design 5b

- **2026-11-08 21:29 UTC [blain]:**
  - **Tasks:** `B-354`.
  - **Summary:** prior-art search recorded in response-log-segments design section 5

- **2026-11-08 21:25 UTC [blain]:**
  - **Tasks:** `B-353`.
  - **Summary:** OpenSpec change response-log-segments, ADR 95-97, backlog B-353..B-391

- **2026-11-08 21:02 UTC [blain]:**
  - **Tasks:** `B-329`.
  - **Summary:** Opened OpenSpec change batched-chunk-writes (proposal, design, tasks, and spec delta)

- **2026-11-08 21:00 UTC [blain]:**
  - **Tasks:** `B-334`.
  - **Summary:** Opened OpenSpec change shared-raw-bytes (proposal, design, tasks, and spec delta)

- **2026-11-08 20:59 UTC [blain]:**
  - **Tasks:** `B-335`.
  - **Summary:** Recorded live feed and boxscore payload normalization cProfile breakdown in download-throughput design.md

- **2026-11-08 06:35 UTC [blain]:**
  - **Tasks:** `B-333`.
  - **Summary:** Dependabot oauthlib alert resolved (4.0.1) and crosswalk fixture tests verified in default gates

- **2026-11-08 06:04 UTC [blain]:**
  - **Tasks:** `B-330`.
  - **Summary:** Live end-to-end streamer replay test with watermark diffing and DuckDB upsert completed and verified

- **2026-11-08 05:58 UTC [blain]:**
  - **Tasks:** `B-327`.
  - **Summary:** Documented provider evidence and added coverage notes for 5 unpopulated MLB datasets

- **2026-11-08 05:44 UTC [blain]:**
  - **Tasks:** `B-332`.
  - **Summary:** Added macos-latest to GitHub Actions CI test matrix

- **2026-11-08 05:42 UTC [blain]:**
  - **Tasks:** `B-319`.
  - **Summary:** Download queue completed: merged spec delta into spec/cli-and-ingest, verified 15 tests, archived change

- **2026-11-08 05:41 UTC [blain]:**
  - **Tasks:** `B-314`.
  - **Summary:** Cross-platform support completed: merged spec/portability, added Platforms section to README, archived change

- **2026-11-08 05:15 UTC [blain]:**
  - **Tasks:** `B-311`.
  - **Summary:** Crosswalk Suite implemented: v_game_crosswalk, v_team_crosswalk, v_venue_crosswalk, and python helpers (bb.games, bb.teams, bb.venues, bb.players) with isolated test suite

- **2026-11-08 05:15 UTC [blain]:**
  - **Tasks:** `B-313`.
  - **Summary:** Python download queue (baseballpy run), games-only job, compaction between stages, history plan, finish-mlb-history change

- **2026-11-08 04:54 UTC [blain]:**
  - **Tasks:** `B-312`.
  - **Summary:** Cross-platform fixes: LF writers, gitattributes, spawn pool, UTF-8 console, enforcing test

- **2026-11-08 04:33 UTC [blain]:**
  - **Tasks:** `B-310`.
  - **Summary:** Committed the B-302 work, fixed the NaN clash, regenerated the project map and coverage matrix

- **2026-11-08 03:33 UTC [blain]:**
  - **Tasks:** `B-261`.
  - **Summary:** Closed out modelling-data-needs per owner directive (out of project scope; sabermetric modeling belongs in sabermetricspy)

- **2026-11-08 01:43 UTC [blain]:**
  - **Tasks:** `B-309`.
  - **Summary:** Typed the game-feed review details and injuryType columns; rare fields and 406-blocked stats_* still in _extras (listed)

- **2026-11-08 01:21 UTC [blain]:**
  - **Tasks:** `B-308`.
  - **Summary:** Memory fix reviewed: bytes in/out manifests, narrow exceptions, spec delta, ADR 88, measurement

- **2026-11-08 00:13 UTC [blain]:**
  - **Tasks:** `B-305`.
  - **Summary:** Reads and views survive older-schema files; compact migrates them and moves _extras values to typed columns (ADR 87)

- **2026-11-07 21:58 UTC [blain]:**
  - **Tasks:** `B-303`.
  - **Summary:** Regenerated MLB schemas: 142 endpoints gained typed name_slug columns; 25 league-wide stats_* left unchanged (406)

- **2026-11-07 21:55 UTC [Gemini]:**
  - **Tasks:** `B-260`.
  - **Summary:** Verified Have column in modelling-data-needs against real lake: 110M Kalshi trades, 14.9M Statcast pitches, 15.8M Retrosheet events, and cataloged missing gaps.

- **2026-11-07 21:28 UTC [Gemini]:**
  - **Tasks:** `B-302`.
  - **Summary:** Implemented Option A qualifiers (rbi_qualifier, attendance_qualifier), null tokens, and parsed 428 raw files; drained quarantine to 0.

- **2026-11-07 21:09 UTC [blain]:**
  - **Tasks:** `B-301`.
  - **Summary:** Resolved manifest save MemoryError using zero-copy binary msgspec serialization in atomic.py; tested roundtrip across 1,000 entries.

- **2026-11-07 04:57 UTC [Gemini (Session 2)]:**
  - **Tasks:** `B-293`.
  - **Summary:** Added baseballpy agent CLI (claim, release, board) with 4-hour stale lock detection, auto 100 MB audit log rotation, and OpenCode deepseek-v4.1-flash-free default.

- **2026-11-06 22:46 UTC [Claude - Session 1]:**
  - **Tasks:** `B-289` (FanGraphs homelab table import; ADR 79).
  - **Summary:** Added `fangraphs` source importing 1,219,323 rows from homelab tables into strongly typed Parquet. Compared column totals with homelab tables; all 9 tests pass. Marked private (no web scraping).

- **2026-11-06 21:50 UTC [Claude - Session 1]:**
  - **Tasks:** `B-288` (Baseball-Reference WAR from published files; ADR 78).
  - **Summary:** Added `bref` source downloading two published WAR files (`war_batting`, `war_pitching`) at 6 requests/minute. Ingested 126,547 batting and 57,884 pitching rows cleanly into typed Parquet.

- **2026-11-06 21:40 UTC [Claude - Session 1]:**
  - **Tasks:** `B-270` (Polymarket source; ADR 77).
  - **Summary:** Added `polymarket` source with catalog (events, markets, outcomes) and hourly prices. All 14 tests pass; schemas and documentation registered.

- **2026-11-06 21:05 UTC [Gemini - Session 2]:**
  - **Tasks:** `B-275`, `B-266`, `B-268` (Kalshi backfill and market decisions; ADR 70, ADR 71).
  - **Summary:** Verified all 447 Kalshi UTC open-date jobs completed cleanly (exit code 0). Ingested 110,994,885 trades and 14,903,320 candlesticks across 900,555 markets. Completed compaction into 11 large Parquet files (3.27 GB total). Verified Python reading via `baseballpy.read`.

---

## Team Notes & Notices

- **Polymarket & BRef are committed:** Polymarket (`B-270`) and Baseball-Reference WAR (`B-288`) are now part of `main`.
- **FanGraphs Policy (ADR 78):** FanGraphs blocks scraping and uses bot challenges. We do not scrape FanGraphs. Any FanGraphs projection data comes strictly from existing homelab archives or user exports.
- **OpenCode Delegation Tool:** `scripts/opencode_delegate.py` is now available for Claude and Gemini to task OpenCode (DeepSeek models) on background briefs with strict `--allow` path protection.
- **Large Audit Log Maintenance:** `.baseballpy/logs/audit.jsonl` (1,255 MB) was successfully rotated and compressed into `audit-2026-11-06.jsonl.gz` (65 MB), freeing ~1.19 GB of disk space. A fresh, empty `audit.jsonl` is active for new requests.
