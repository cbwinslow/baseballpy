## ADDED Requirements

### Requirement: A Plan Can Be Run One Stage At A Time
`baseballpy backfill PLAN --stage X` (repeatable) MUST run only the stages named by `X`, a stage name or its 1-based number, in plan order, and MUST refuse an unknown stage before anything runs.

#### Scenario: Choosing stages
- **WHEN** a plan with three stages is run with `--stage` naming the second by name and the third by number, and with an unknown name
- **THEN** only those two stages are planned, in plan order, and the unknown name is refused with the list of stages
- Verified by `tests/test_queue.py::test_select_stages_by_name_and_number` and `tests/test_queue.py::test_select_stages_refuses_an_unknown_stage`.

### Requirement: A Python Supervisor Keeps A Plan Running
`baseballpy run PLAN` MUST run each stage of the plan in its own child process, retry a failed stage with exponential backoff and jitter up to `--retries` times, continue with the next stage when one is out of retries, and record the round, each stage's status, attempts and last error in a state file under the lake home. It MUST NOT retry a stage that stopped because of a disk or size limit. With `--every` it MUST start a new round after that interval and keep going until stopped; without it, it MUST end when the plan is done. It MUST depend on no operating-system scheduler.

#### Scenario: Retries, order and rounds
- **WHEN** a stage fails twice and then succeeds, another fails every time, and a third follows
- **THEN** the first stage is tried three times, the second is marked failed after its retries, the third still runs, and the exit code is 1
- Verified by `tests/test_queue.py::test_a_failed_stage_is_retried_and_does_not_block_the_next` and `tests/test_queue.py::test_a_stage_stopped_by_a_limit_is_not_retried`.

#### Scenario: Repeating and stopping
- **WHEN** the queue runs with an interval and the stop event is set during the wait
- **THEN** a second round runs after the interval, and the queue ends with exit code 130 without starting another
- Verified by `tests/test_queue.py::test_every_starts_new_rounds_until_stopped`.

### Requirement: A Restarted Supervisor Resumes The Unfinished Round
The supervisor MUST keep its state in an atomically written file and, when started again for the same plan with a round unfinished, MUST skip the stages already done in that round. Only one supervisor MUST run per lake home.

#### Scenario: Resume and single instance
- **WHEN** the queue is stopped after its first stage and started again, and a second supervisor is started while one runs
- **THEN** the first stage is not run again, and the second supervisor is refused with a clear message
- Verified by `tests/test_queue.py::test_a_restart_skips_the_stages_already_done` and `tests/test_queue.py::test_only_one_supervisor_runs_per_home`.

#### Scenario: Child process
- **WHEN** a stage is run by the child-process runner
- **THEN** it starts the current Python (`sys.executable`) with the `backfill` command and `--stage`, maps its exit code, and terminates the child when the stop event is set
- Verified by `tests/test_queue.py::test_the_child_runner_uses_the_current_python_and_stops_the_child`.
