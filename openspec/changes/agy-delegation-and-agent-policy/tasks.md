# Tasks: agy Delegation and Agent Policy

- [x] 1. Wrapper `scripts/agy_delegate.py` and smoke test (headless print mode)
- [x] 2. `docs/agents/AGY_DELEGATION.md`
- [x] 3. Policy text in CLAUDE.md, AGENTS.md section 13, GOAL_SEEK_PROMPT.md
- [x] 4. First real delegations (ingest core, adapters, CLI commands) reviewed and gated 2026-10-27. Findings: print mode denies agy's shell commands and a denied call ends its turn with an empty answer, so the wrapper defaults to emit mode (plan mode, files returned in the answer, written only under --allow prefixes), retries on denied actions, and never uses --dangerously-skip-permissions. Review caught: swallowed exceptions (scan_lake, disk usage), a TypeError-masking loader cascade, hasattr-based guessing
