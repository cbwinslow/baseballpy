## ADDED Requirements

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
