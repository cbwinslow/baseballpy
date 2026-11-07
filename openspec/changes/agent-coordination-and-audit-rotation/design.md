# Design: Agent Coordination, Audit Rotation & Synergized Multi-Agent Workflow

## Architecture & Interfaces

### 1. Agent Coordination CLI (`src/baseballpy/cli_agent.py`)

A new Click command group `baseballpy agent` is registered in `src/baseballpy/cli.py`:

```bash
baseballpy agent claim <task_id> [--agent <name>] [--files <paths>] [--note <text>]
baseballpy agent release <task_id> "<summary>"
baseballpy agent board
```

#### Lock Semantics & Stale Detection
- An active checkout is identified by `task_id` (e.g. `B-293`).
- When claiming:
  - Read `docs/agents/AGENT_BOARD.md` and check `docs/agents/agent_log.jsonl`.
  - If the task or overlapping files are already claimed:
    - If claimed timestamp is < 4 hours ago, abort with exit code 1 (`Error: Task <task_id> is locked by <agent> since <timestamp>`).
    - If claimed timestamp is >= 4 hours ago, print a warning, record `STALE_LOCK_OVERRIDDEN` in `agent_log.jsonl`, and permit override.
  - Upon successful claim:
    - Write markdown block to `docs/agents/AGENT_BOARD.md` under `## Active Checkouts (Locked — Do Not Disturb)`.
    - Append JSON record to `docs/agents/agent_log.jsonl` with event `TASK_CLAIMED`.
- When releasing:
  - Find active entry in `docs/agents/AGENT_BOARD.md`.
  - Remove from `## Active Checkouts` and prepend to `## Recent Completed Handoffs` with date, agent, task ID, and summary.
  - Append JSON record to `docs/agents/agent_log.jsonl` with event `TASK_COMPLETED`.

### 2. Audit Log Rotation (`src/baseballpy/core/audit.py` & `src/baseballpy/cli_audit.py`)

#### Rotation Policy
- **Default Threshold:** 100 MB (`100 * 1024 * 1024` bytes).
- **File Naming:** `.baseballpy/logs/audit-YYYY-MM-DD.jsonl.gz`. If multiple rotations occur on the same day, append an incremental sequence: `audit-YYYY-MM-DD-N.jsonl.gz`.
- **Atomic Rotation Algorithm:**
  1. Check file size of `.baseballpy/logs/audit.jsonl`.
  2. If file size >= threshold (or `--force` flag passed):
     - Atomically rename `audit.jsonl` to temporary file `audit.jsonl.rot`.
     - Touch new empty `audit.jsonl`.
     - Compress `audit.jsonl.rot` using Python's standard `gzip` into final `.jsonl.gz` target.
     - Remove temporary `audit.jsonl.rot`.
     - Append `AUDIT_ROTATED` event to `docs/agents/agent_log.jsonl`.
- **CLI Command:**
  - `baseballpy audit rotate [--max-mb 100] [--force]`

### 3. OpenCode Model Delegation

- `scripts/opencode_delegate.py` default model is set to `opencode/deepseek-v4.1-flash-free`.
- Evaluated alternative free models on OpenCode:
  - `opencode/deepseek-v4.1-flash-free`: Primary (highest coding & reasoning benchmark scores).
  - `opencode/glm-5.3-flash-free`: Secondary fallback.
  - `opencode/nemotron-3.5-lightning-free`: Tertiary fallback.

### 4. Tripartite Workflow Synergy
The development lifecycle links three tracking systems without duplication:
1. **OpenSpec Changes (`openspec/changes/<change>/tasks.md`):** Granular engineering tasks.
2. **Backlog (`docs/agents/BACKLOG.md`):** Single prioritized queue with `B-xxx` identifiers. Enforced by `tests/test_agent_runbooks.py`.
3. **Agent Board (`docs/agents/AGENT_BOARD.md`):** Dynamic runtime coordination with active checkouts and completed handoffs.
