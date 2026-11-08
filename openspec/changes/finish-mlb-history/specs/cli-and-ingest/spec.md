## ADDED Requirements

### Requirement: Compaction Runs Beside The Next Download, One At A Time
`baseballpy run` MUST run the after-stage step (compaction) of a finished stage in the background while the next stage runs, MUST start the next after-stage step only when the previous one has ended, MUST wait for the last one before it returns, and MUST record a failed step in the stage's last error without failing the stage. `baseballpy compact` MUST compact up to `--jobs` datasets at the same time.

#### Scenario: Overlap
- **WHEN** three stages finish and each has an after-stage step, and the step of the first waits until the second stage has started
- **THEN** the second stage starts while the first step runs, no two steps run at once, and the queue returns only after the last step
- Verified by `tests/test_queue.py::test_compaction_runs_beside_the_next_stage_and_never_beside_another_compaction` and `tests/test_queue.py::test_a_finished_stage_is_compacted_and_a_compact_failure_does_not_fail_it`.
