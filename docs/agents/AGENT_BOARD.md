# AI Agent Bulletin Board & Coordination Center

This board coordinates parallel and multi-session AI agents (Claude Code, Gemini/Antigravity, Cursor, etc.) working on `baseballpy`.

---

## Operating Rules for All Agents

1. **Read First:** Before touching or modifying any files, read `## Active Checkouts` below.
2. **Never Clobber:** If a file or task is listed under `Active Checkouts`, DO NOT modify, overwrite, or delete those files. Pick an unassigned task from `docs/agents/BACKLOG.md` instead.
3. **Claim Before Coding:** When starting a task, add your checkout tag to `## Active Checkouts` and append an entry to `docs/agents/agent_log.jsonl`.
4. **Log on Completion:** When your slice or task is finished:
   - Move your entry from `Active Checkouts` to `Recent Completed Handoffs` with a clear 2-sentence summary.
   - Append a `TASK_COMPLETED` record to `docs/agents/agent_log.jsonl`.
   - Update `docs/agents/BACKLOG.md` and run `uv run python scripts/project_map.py`.

---

## Active Checkouts (Locked — Do Not Disturb)

- **Task:** FanGraphs homelab export & schema generation
  - **Agent:** Claude (Session 1)
  - **Claimed At:** 2026-11-06 22:00 UTC
  - **Locked Areas:**
    - `src/baseballpy/sources/fangraphs/`
    - `scripts/export_homelab_fangraphs.py`
    - `scripts/gen_fangraphs_schemas.py`
    - `docs/sources/fangraphs.md`
  - **Status:** Creating scripts to inspect/export FanGraphs tables from the homelab and generate strongly typed schemas without web scraping (per ADR 78). In progress.

---

## Recent Completed Handoffs

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
