## ADDED Requirements

### Requirement: Job Prerequisites
A planned job MAY name the jobs that must finish before it starts (`Job.needs`, job ids; ids not in the plan are ignored because the data is then read from the lake as it is). The runner MUST start such a job only after those jobs finished, in the sequential and the pooled path, and MUST keep the results in planned order. A job whose prerequisite failed or was cancelled MUST be reported `failed` with the prerequisite named, without running, and one audit event MUST still be written for it. Jobs that wait for each other MUST be rejected before anything runs. The MLB adapter MUST declare these prerequisites from the endpoint registry (`prerequisites(endpoint)`), never from a hard-coded name list, and an endpoint whose fan-out values are not in the lake MUST log a warning that nothing was requested.

#### Scenario: A dependent job waits even with many workers
- **GIVEN** a roster job planned before the teams job it needs, and four workers
- **WHEN** the plan runs
- **THEN** the teams job runs first, the roster job second, and the results keep the planned order.
- Verified by `tests/test_request_parallelism.py::test_a_dependent_job_waits_for_its_prerequisite_even_with_many_workers`.

#### Scenario: A failed prerequisite fails its dependents visibly
- **GIVEN** a teams job that raises and a roster job that needs it
- **WHEN** the plan runs sequentially or on a pool
- **THEN** the roster job is `failed` with the prerequisite named and was not run.
- Verified by `tests/test_request_parallelism.py::test_a_dependent_of_a_failed_job_fails_visibly_without_running`.

#### Scenario: A cycle is rejected
- **WHEN** two jobs need each other
- **THEN** `ValueError` naming the cycle is raised and no job ran.
- Verified by `tests/test_request_parallelism.py::test_jobs_that_wait_for_each_other_are_rejected_before_anything_runs`.

#### Scenario: Independent jobs run in parallel
- **GIVEN** six independent jobs and three workers
- **WHEN** they run
- **THEN** three are in flight at once.
- Verified by `tests/test_request_parallelism.py::test_independent_jobs_do_run_in_parallel`.

#### Scenario: The MLB planner orders a fan-out endpoint after its teams
- **GIVEN** `--datasets team_roster_active teams_season` for 2024
- **WHEN** the adapter plans
- **THEN** the roster job needs the `teams_season` job, and needs nothing when `teams_season` is not planned.
- Verified by `tests/test_request_parallelism.py::test_the_planner_orders_a_fan_out_endpoint_after_its_teams` and `::test_prerequisites_come_from_the_scope_and_the_placeholders`.

#### Scenario: An empty fan-out is not a silent success
- **WHEN** a team-scoped endpoint runs and no teams are in the lake
- **THEN** a warning names the missing prerequisite dataset.
- Verified by `tests/test_request_parallelism.py::test_an_empty_fan_out_is_warned_about_not_silently_completed`.

### Requirement: The CLI States the Network Limit
`baseballpy ingest` MUST print the number of job workers and the per-host in-flight limit that applies to the network, because `--concurrency` sizes only the job workers.

#### Scenario: Workers and limit are shown
- **WHEN** `ingest -c 3` runs with `BASEBALLPY_RATE_MAX_CONCURRENCY=6`
- **THEN** the output says 3 parallel workers and up to 6 requests in flight per host.
- Verified by `tests/test_cli_ingest.py::test_the_cli_states_the_workers_and_the_real_network_limit`.
