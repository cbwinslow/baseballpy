## ADDED Requirements

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
