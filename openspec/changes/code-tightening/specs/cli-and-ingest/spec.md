## ADDED Requirements
### Requirement: Season Selections Are Validated
A season selection (`2023`, `2015-2024`, `2015,2018`, `all`) MUST resolve to a sorted tuple of unique years between 1800 and 2100, and any other text (empty, non-numeric, reversed range, malformed range, out of range, `all` without a source of seasons) MUST raise a `ValueError` that names the bad text.

#### Scenario: Bad selections are refused
- **WHEN** a selection is empty, reversed, malformed, non-numeric or outside 1800..2100
- **THEN** a `ValueError` is raised and nothing is planned.
- Verified by `tests/test_ingest_selection.py::test_parse_reversed_range_raises` and `tests/test_ingest_selection.py::test_parse_out_of_bounds_raises` and `tests/test_ingest_selection.py::test_parse_malformed_syntax_raises`.

#### Scenario: Good selections resolve in order
- **WHEN** a selection mixes ranges, single years and duplicates
- **THEN** the years come back sorted and unique.
- Verified by `tests/test_ingest_selection.py::test_parse_sorting_and_deduplication`.
