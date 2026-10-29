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

### Requirement: Binding Agent Operating Rules
`AGENTS.md` MUST contain the agent operating rules (preflight, hard rules, banned patterns, definition of done, when blocked), `CLAUDE.md` MUST repeat the hard rules and point to them, and `docs/agents/TOOLING.md` MUST list every runtime dependency as a designated tool with the reuse check, so that an agent checks the designated tools before writing code.

#### Scenario: Rules and tools table are present
- **WHEN** `AGENTS.md`, `CLAUDE.md`, `pyproject.toml` and `docs/agents/TOOLING.md` are read
- **THEN** `AGENTS.md` has section 14 with its five subsections, `CLAUDE.md` has the hard rules and links to the tools table and work breakdown, and every runtime dependency appears in the tools table
- Verified by `tests/test_agent_rails.py::test_agents_md_has_the_operating_rules`, `tests/test_agent_rails.py::test_claude_md_states_the_hard_rules_and_points_to_the_tools_table` and `tests/test_agent_rails.py::test_every_runtime_dependency_is_in_the_tooling_table`.

#### Scenario: Banned libraries stay out of the source
- **WHEN** the modules under `src/baseballpy` are parsed
- **THEN** none imports `requests`, `aiohttp`, `urllib.request` or `pandas`
- Verified by `tests/test_agent_rails.py::test_source_code_uses_no_banned_libraries`.

### Requirement: Task Cards Mirror OpenSpec Tasks
Source work MUST be cut into task cards under `docs/agents/tracks/`, each with the fields change task, stage, executor, files, tools, inputs, steps, done-when and record, and each naming an existing task of an OpenSpec change.

#### Scenario: Every card is complete and traceable
- **WHEN** the cards under `docs/agents/tracks/` are parsed
- **THEN** each has every field and its `Change task` points at a numbered task of an existing change
- Verified by `tests/test_agent_rails.py::test_task_cards_exist_and_have_every_field` and `tests/test_agent_rails.py::test_every_card_names_a_real_change_task`.

### Requirement: Source Reviews Come From One Table
Every source MUST be reviewed with the same standard tasks, rendered from one table by `scripts/new_source_review.py` into an OpenSpec change, a task-card file and backlog rows, covering inventory, registry conformance, schema against data, code against the designated tools, the shared currency check, full Python access, tests and spec, a clean live run, the export checklist, cited column descriptions and the close-out; the generator MUST refuse to overwrite existing files, and `docs/agents/PROJECT_MAP.md` MUST carry a generated scorecard with one row per source.

#### Scenario: Complete, traceable cards for every source
- **WHEN** the review is rendered for each source
- **THEN** every card has all required fields, the task numbers match the cards, no placeholder is left, and the standing standards (shared currency check, upstream check, export checklist, cited descriptions, registry-driven names, schema-sync test) appear in the tasks
- Verified by `tests/test_new_source_review.py::test_every_source_gets_complete_cards_that_match_its_tasks` and `tests/test_new_source_review.py::test_standing_standards_are_in_every_review`.

#### Scenario: Backlog numbering and no overwriting
- **WHEN** the generator runs twice for one source
- **THEN** the backlog rows continue the existing numbering and chain the tasks, and the second run refuses and changes nothing
- Verified by `tests/test_new_source_review.py::test_backlog_rows_continue_the_numbering_and_chain_the_tasks` and `tests/test_new_source_review.py::test_generator_writes_the_files_once_and_refuses_to_overwrite`.

#### Scenario: Scorecard shows where each source stands
- **WHEN** the project map is generated
- **THEN** it has one row per source in review order with review state, track cards, shared currency, fingerprints, description coverage and spec size, and the file is kept current by a test
- Verified by `tests/test_new_source_review.py::test_scorecard_has_one_row_per_source_in_review_order` and `tests/test_agent_runbooks.py::test_project_map_is_current`.
