## ADDED Requirements

### Requirement: A Stage Whose After-Step Failed Is Not Done
When the after-step of a finished stage (compaction) exits with a non-zero code, the supervisor MUST mark the
stage `failed` with the error recorded, MUST include it in the failed stages of the round (so the exit code
is 1 and `status` shows it), and MUST run it again like any failed stage. A stage is `done` only when its
download and its after-step both succeeded.

#### Scenario: A failed compaction is retried and reported
- **WHEN** a stage downloads fine but its after-step fails once and then succeeds, with an interval set
- **THEN** the stage is failed and the round's exit code is 1 after the first pass, it runs again in the same
  round, and it ends done
- Verified by `tests/test_queue.py::test_a_failed_after_step_fails_the_stage_and_it_runs_again`.

#### Scenario: The last stage's after-step counts
- **WHEN** the last stage of a round has a failing after-step
- **THEN** the report lists that stage as failed
- Verified by `tests/test_queue.py::test_the_last_stages_after_step_is_settled_before_the_report`.
