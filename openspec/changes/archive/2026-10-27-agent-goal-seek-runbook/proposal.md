# Change Proposal: Agent Goal-Seek Runbook (Deployable Prompt with Verification Loops)

## Context & Motivation
Long autonomous runs on this repo repeatedly needed the same corrections: read `AGENTS.md` first, open an OpenSpec change before editing, never leave upstream data behind, do not trust a first `unsupported` verdict, run the gates, keep the specs, ADRs and tasks in sync, avoid broad process kills, and use web search when a fact (a format, an endpoint, a parameter) is not in the repo. These instructions lived in chat history. They belong in a versioned, deployable prompt.

## Proposed Changes
1. `docs/agents/GOAL_SEEK_PROMPT.md`: a fill-in-the-blanks goal prompt with an explicit PLAN - IMPLEMENT - VERIFY - AUDIT - RECORD - COMMIT loop, stop conditions, a web-research protocol, and a definition of done.
2. A short pointer from `CLAUDE.md` and `AGENTS.md` section 12.
3. The prompt is itself covered by this OpenSpec change (AGENTS.md section 12), reviewed whenever the contract changes.

## Out of Scope
Tooling that launches the prompt automatically; subagent orchestration (the owner's standing rule is no subagents).

## Impact
Docs only.
