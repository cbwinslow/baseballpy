# Agent Coordination, Audit Log Rotation, and Synergized Multi-Agent Workflow

## Why
As development on `baseballpy` scales with multiple concurrent AI agents (Claude Code, Gemini/Antigravity, Cursor, and OpenCode running DeepSeek models), coordination friction poses real risks:
1. Two sessions may unintentionally edit the same files or duplicate research on the same source (splash damage and merge conflicts).
2. The network telemetry audit log (`.baseballpy/logs/audit.jsonl`) can swell rapidly during massive data ingestions (such as Kalshi's 447-day backfill, reaching 1.25 GB), consuming excessive disk and degrading audit query throughput.
3. Task queues need seamless alignment: backlog items (`B-xxx`), OpenSpec change tasks (`tasks.md`), and active agent checkouts (`docs/agents/AGENT_BOARD.md`) must be linked systematically so human owners and autonomous agents always have a unified source of truth.
4. Delegation to local OpenCode engines requires a standard, capable free model default (`opencode/deepseek-v4.1-flash-free`) under a strict "Chief of Staff" review model.

## What Changes
1. **Agent CLI (`baseballpy agent`):**
   - Provide `baseballpy agent claim <task_id> [--agent <name>] [--files <paths>] [--note <text>]` to atomically acquire task locks.
   - Provide `baseballpy agent release <task_id> "<summary>"` to complete and move active checkouts to recent handoffs.
   - Provide `baseballpy agent board` to display active locks, recent handoffs, and warnings for stale checkouts (> 4 hours old) using Rich formatting.
   - Synchronize with both human-readable `docs/agents/AGENT_BOARD.md` and machine-readable `docs/agents/agent_log.jsonl`.
2. **Automated Audit Log Rotation (`baseballpy audit rotate`):**
   - Provide CLI command and automatic check: when `.baseballpy/logs/audit.jsonl` exceeds 100 MB, rotate and compress into `audit-YYYY-MM-DD.jsonl.gz` using standard `gzip`, maintaining a clean, empty active log file.
3. **Synergized Workflow & Operating Rules:**
   - Formalize the linkage between OpenSpec `tasks.md`, `docs/agents/BACKLOG.md`, and `docs/agents/AGENT_BOARD.md`.
   - Set `scripts/opencode_delegate.py` default model to `opencode/deepseek-v4.1-flash-free`.
   - Update `AGENTS.md` and `CLAUDE.md` operating mandates.
