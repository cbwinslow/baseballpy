## ADDED Requirements

### Requirement: A Sample Download Is Compared With The Lake
`baseballpy verify-sample SOURCE` MUST download the selected sample into a fresh scratch home without touching
the real lake, then compare it with the lake: every completed processed chunk of the sample against the same
chunk of the lake (rows sorted by the registered keys, registered columns) and every raw file's sha256 against
the lake's record. It MUST report identical chunks, differing chunks (with the first differing column), chunks
the lake lacks and raw files whose bytes differ, and MUST exit non-zero when any chunk or raw file differs.

#### Scenario: Identical, changed and missing chunks
- **WHEN** a sample lake is compared with a lake that holds the same chunks, then with one that has a changed value, a missing chunk and a changed raw checksum
- **THEN** the first comparison is all identical, and the others report the changed chunk and its column, the missing chunk and the changed raw file, and the command exits 1 for the differences
- Verified by `tests/test_sample_compare.py::test_identical_lakes_compare_identical`, `tests/test_sample_compare.py::test_a_changed_value_a_missing_chunk_and_a_changed_raw_file_are_reported` and `tests/test_sample_compare.py::test_the_verify_sample_command_exits_one_on_a_difference`.
