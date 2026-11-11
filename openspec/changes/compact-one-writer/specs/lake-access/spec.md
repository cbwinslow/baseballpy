## ADDED Requirements

### Requirement: One Compaction Per Dataset At A Time
`compact_dataset` (and so `baseballpy compact` and the download queue's stage compaction) MUST take an
operating-system lock named for the dataset (`compact-<source>-<dataset>` in the lake's locks folder)
before it changes any file, and MUST give it back when it ends. A second compaction of the same dataset
MUST be refused with a clear message and MUST change no file and no record; compaction of other datasets
MUST NOT be blocked. A dry run MUST NOT need the lock. `baseballpy compact` MUST report a refused dataset
as skipped and exit non-zero after the other datasets are done.

#### Scenario: A second compaction of the same dataset is refused
- **WHEN** another process holds the compaction lock of a dataset and `compact_dataset` runs for it
- **THEN** it raises `HostBusyError`, no file or record changes, and after the holder ends (even by a
  crash) the dataset compacts normally
- Verified by `tests/test_compact_lock.py::test_a_second_compaction_of_one_dataset_is_refused_and_changes_nothing`.

#### Scenario: The command skips a busy dataset
- **WHEN** `baseballpy compact` is run for a dataset another process is compacting
- **THEN** it prints that the dataset was skipped because it is busy and exits with a non-zero code
- Verified by `tests/test_compact_lock.py::test_the_compact_command_skips_a_busy_dataset_and_fails`.
