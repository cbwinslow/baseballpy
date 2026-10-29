# Proposal: project-replan-and-agent-rails

## Why
The owner asked for a review from the start: map how the project works, partition it into small
tasks any AI agent can finish, harden the operating contract so agents always use the designated
tools, always document in OpenSpec and keep code flexible and reusable, then work one source at a time.

Findings of the review (2026-10-29, from reading `AGENTS.md`, `CLAUDE.md`, `openspec/`, `docs/`,
the backlog and the tests):

1. The rules exist but are spread over `AGENTS.md`, `CLAUDE.md`, `GOAL_SEEK_PROMPT.md`,
   `AGY_DELEGATION.md` and `EXECUTION_ORDER.md`, and nothing tells an agent to check the designated
   tools before writing code. Import counts show the effect: stdlib `csv` in 5 modules, stdlib `json`
   in 22 while `msgspec` is in 4, `narwhals` in 2.
2. Only part of the contract is enforced by tests (import boundaries, swallowed exceptions, unsafe
   casts, spec citations, backlog mapping). Tool-first, task-card and doc-sync rules are prose only.
3. The backlog is ordered by history, not by source; tasks are large (B-43 is a redesign, B-35 a
   homelab run). There is no uniform per-source review, so quality differs by source.
4. Doc drift: `EXECUTION_ORDER.md` lists archived changes as pending; `openspec/project.md` names
   modules that do not exist; `BACKLOG.md` carried a duplicated row; `AGENTS.md` gives
   `~/.baseballpy/...` paths where the lake lives under `$BASEBALLPY_HOME`.
5. Suspected defect found while reading: the Chadwick adapter hard-codes one dataset name while the
   registry has four (handled in `chadwick-source-review`).

## What changes
- `docs/agents/TOOLING.md`: the designated-tools table and the reuse check.
- `docs/agents/WORK_BREAKDOWN.md`: how the project works, the recursive partition, the seven stages
  every source goes through, the task-card format; `docs/agents/tracks/01-chadwick.md`: the first track.
- `AGENTS.md` section 14 (binding agent operating rules) and a hard-rules block in `CLAUDE.md`.
- `tests/test_agent_rails.py`: enforces the new rules that can be checked mechanically.
- Backlog reorganised around tracks; new change `chadwick-source-review`; doc drift fixed.

## Out of scope
Rewriting working code, adding the CSV sink, the dlt redesign (BACKLOG B-43), any source other than Chadwick.

## Impact
Docs, one test file, one spec delta (`agent-runbooks`). No runtime code.
