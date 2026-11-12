## ADDED Requirements

### Requirement: No Value Of The Provider's Text Is Lost Or Changed
`baseballpy verify-roundtrip` MUST compare sampled raw CSV files with the processed rows cell by cell (integers by their
text, floats by value as 64-bit floats, dates by their format, text exactly), report non-empty raw cells stored as NULL,
raw rows missing from the processed data and raw columns no schema column or `_extras` reads, list datasets it cannot
read as skipped with the reason, and exit 1 on any loss; no registered column MAY be a 32-bit float, and a number
written with a leading zero or a plus sign MUST be typed as text.

#### Scenario: Each kind of loss is caught and a clean dataset passes
- **WHEN** a dataset is checked whose stored cells are equal, or whose float is 32-bit, whose integer dropped a leading zero, whose cell became NULL, whose row is missing or whose raw column is unread
- **THEN** the equal dataset is `ok` and each of the others reports its own kind of loss with an example; a dataset with raw files that are not CSV is `skipped`
- Verified by `tests/test_roundtrip.py::test_equal_cells_pass_and_the_extra_column_is_accounted_for`, `tests/test_roundtrip.py::test_a_32_bit_float_is_a_changed_cell`, `tests/test_roundtrip.py::test_a_dropped_leading_zero_is_a_changed_cell`, `tests/test_roundtrip.py::test_a_value_turned_into_null_and_a_missing_row_are_reported`, `tests/test_roundtrip.py::test_a_raw_column_nothing_reads_is_a_loss_unless_extras_holds_it` and `tests/test_roundtrip.py::test_a_dataset_without_csv_raw_files_is_skipped_with_a_reason`.

#### Scenario: Repeated keys and the type rules
- **WHEN** keys repeat in the processed rows, the type guesser sees `01405134`, and the registry is scanned for 32-bit floats
- **THEN** the comparison uses multisets and ignores overlapping windows, the guesser answers text, and no column is a 32-bit float
- Verified by `tests/test_roundtrip.py::test_repeating_keys_are_compared_as_multisets_and_overlapping_windows_are_not_a_loss`, `tests/test_infer_types.py::test_numbers_with_leading_zeros_or_a_plus_sign_are_text` and `tests/test_schema_rules.py::test_no_registered_column_is_a_32_bit_float`.
