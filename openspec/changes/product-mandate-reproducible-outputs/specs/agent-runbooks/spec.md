## ADDED Requirements

### Requirement: The Contract States The Product And Reproducible Outputs
`AGENTS.md` MUST open with a "Product mission" section (a reusable Python library, distributed on PyPI, that
downloads, ingests and maintains historical and real-time MLB data for other people, and whose lake is a
test oracle, not the deliverable) and MUST contain a "Reproducible outputs" section (the same inputs give
the same rows, schema, names and bytes for every user and run; a data defect is fixed in the code path
that produced it, with a test, and the data is rebuilt by the workflow; hand edits of data files are a last
resort). `CLAUDE.md` and `openspec/project.md` MUST state the mission.

#### Scenario: The mandate cannot be removed unnoticed
- **WHEN** the mission or reproducibility sections are removed from the contract files
- **THEN** the test suite fails
- Verified by `tests/test_agent_rails.py::test_the_contract_states_the_product_and_reproducibility_mandate`.
