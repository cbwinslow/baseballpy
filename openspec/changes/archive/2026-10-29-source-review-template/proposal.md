# Proposal: source-review-template

## Why
The owner asked (2026-10-29) how to make sure every later source follows the pattern set by Chadwick and
that work can be resumed after a break. Hand-copying the Chadwick cards would drift.

## What changes
`scripts/new_source_review.py` renders the standard review (change, tasks, task cards, backlog rows) for
any source from one table of standard tasks; `scripts/project_map.py` adds a generated scorecard (review
state, track cards, shared currency check, fingerprints, column-description coverage, spec size per
source) to `docs/agents/PROJECT_MAP.md`; `docs/agents/NEXT_GOAL.md` says how to resume.

## Impact
Tooling and docs only. Spec delta on `agent-runbooks`.
