# Change Proposal: agy Delegation and Agent Policy

## Context & Motivation
The owner wants Claude to act as architect and reviewer and to delegate bulk code writing to Gemini through the Antigravity CLI (`agy`), to save tokens and time; to keep the codebase decoupled and dynamic; and to web-search for existing solutions before building workarounds.

## Proposed Changes
1. `scripts/agy_delegate.py` (headless `agy -p`, accept-edits, JSON result, `git diff --stat`, never commits) and `docs/agents/AGY_DELEGATION.md` (when to delegate, brief template, mandatory review).
2. Policy text in `CLAUDE.md`, `AGENTS.md` section 13 and `docs/agents/GOAL_SEEK_PROMPT.md` (design philosophy, search-first, delegation); the "no subagents" owner rule now exempts `agy`.

## Out of Scope
ACP/MCP integration (not needed: print mode suffices); Claude `Agent`/workflow subagents stay off.

## Impact
Documentation and one script; no library code.
