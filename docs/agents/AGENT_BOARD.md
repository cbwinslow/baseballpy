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

- **Task:** B-261
  - **Agent:** Gemini
  - **Claimed At:** 2026-11-07 22:08 UTC
  - **Locked Areas:**
    - `openspec/changes/modelling-data-needs/design.md`
    - `openspec/changes/modelling-data-needs/tasks.md`
  - **Status:** Recording modeling decisions D1 to D6

---

## Recent Completed Handoffs

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
