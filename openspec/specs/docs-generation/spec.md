# Docs Generation Specification

## Purpose
Generated documentation (column dictionaries, CLI reference) cannot drift from the code, and every description is traceable to its source.

## Requirements

### Requirement: Column Descriptions With Provenance
Every column of every generated dictionary MUST show a description taken from provider metadata or marked `TODO`; each description MUST cite its source (or be flagged `authored`); the described-column count MUST never decrease (ratchet test) and `baseballpy docs coverage` MUST report it per source.

#### Scenario: Missing descriptions are marked and cited
- **WHEN** a dictionary is rendered
- **THEN** each column shows its description with its source, or `TODO` when none exists, and the described count never drops below the committed baseline
- Verified by `tests/test_docs_descriptions.py::test_render_marks_missing_cites_sources_and_escapes_pipes and ::test_described_columns_never_drop_below_the_committed_baseline`.
