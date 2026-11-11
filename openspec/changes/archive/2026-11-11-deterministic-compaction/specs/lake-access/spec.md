## ADDED Requirements

### Requirement: Compaction Is Deterministic
Compacting the same chunks in one run MUST produce byte-identical compacted files whatever order the chunks
were downloaded in; a rerun MUST rewrite nothing; and compacting at different times MUST leave the same
rows (the grouping into files may differ, and a reader must not depend on row order).

#### Scenario: Another download order gives the same files
- **WHEN** the same four chunks are stored in two lakes in opposite order and each is compacted
- **THEN** the compacted files have the same names and the same sha256
- Verified by `tests/test_compact_deterministic.py::test_the_same_chunks_give_byte_identical_files_whatever_the_download_order`.

#### Scenario: A rerun and a staged run
- **WHEN** a compacted dataset is compacted again, and another lake is compacted in two stages
- **THEN** the rerun rewrites nothing and both lakes hold the same rows
- Verified by `tests/test_compact_deterministic.py::test_a_rerun_rewrites_nothing` and `tests/test_compact_deterministic.py::test_compacting_at_different_times_gives_the_same_rows`.
