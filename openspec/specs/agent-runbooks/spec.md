# Agent Runbooks Specification

## Purpose
Keeps autonomous runs repeatable: one versioned prompt states the contract, the verification and the recording rules.

## Requirements

### Requirement: Versioned Goal-Seek Prompt
The repository MUST contain a deployable goal-seek prompt that requires reading the contract files first, opening an OpenSpec change before editing, verifying with the gates and live evidence, auditing for data left behind and for unverified `unsupported` verdicts, recording tasks/ADRs/specs, committing per section without pushing, and using cited web research for facts the repository cannot answer.

#### Scenario: Prompt keeps the required rules
- **WHEN** `docs/agents/GOAL_SEEK_PROMPT.md` is read
- **THEN** it names `AGENTS.md`, requires an OpenSpec change, forbids leaving upstream data behind, demands evidence for `unsupported`, forbids pushing and orders a web search before any workaround, inside a PLAN/verify loop with pytest, ruff and mypy
- Verified by `tests/test_agent_runbooks.py::test_goal_seek_prompt_states_every_required_rule`.
