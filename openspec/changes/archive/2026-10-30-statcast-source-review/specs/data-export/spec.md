## ADDED Requirements

### Requirement: Read-Back Compares Dictionary Columns As Values
The export read-back check MUST treat a dictionary-encoded column as equal to the source when the values are equal, whatever dictionaries the stored parts used.

#### Scenario: Parts with different dictionaries verify
- **WHEN** a dataset stored in two parts whose text categories have different dictionaries is exported to Parquet or CSV
- **THEN** the export verifies
- Verified by `tests/test_export.py::test_dictionary_columns_with_different_dictionaries_per_stored_part_verify`.
