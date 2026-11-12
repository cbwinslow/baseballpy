## ADDED Requirements

### Requirement: Concurrency Follows Live, Measured Memory
The job runner MUST start another job only while the free memory above a reserve that is a share of the machine covers
the memory growth measured for the jobs already running, MUST always allow the first job, MUST treat the smaller of
free RAM and the operating system's commit headroom as the memory available, MUST audit-log when jobs are held back,
and a process-pool worker MUST exit when its parent process is gone; the worker count MUST only be an upper bound.

#### Scenario: Plenty of memory runs jobs side by side, scarce memory holds them back
- **WHEN** six jobs of 1 GB each run with 90 GB free, and five jobs with only 17 GB free of a 96 GB machine
- **THEN** several jobs run at once in the first case, at most two in the second, and all jobs finish in both
- Verified by `tests/test_memguard.py::test_the_runner_runs_jobs_side_by_side_when_memory_is_plentiful` and `tests/test_memguard.py::test_the_runner_holds_jobs_back_when_memory_is_scarce_and_still_finishes`.

#### Scenario: Admission follows measured growth, commit headroom and the reserve
- **WHEN** one running job has grown the process by 3 GB and the free memory, the commit headroom and the machine size change
- **THEN** another job starts only while the free memory above the reserve covers 1.5 times that growth, the commit headroom counts as memory, and the first job always starts
- Verified by `tests/test_memguard.py::test_admission_follows_the_measured_growth_and_the_live_free_memory`, `tests/test_memguard.py::test_the_operating_system_commit_headroom_counts_as_memory` and `tests/test_memguard.py::test_the_first_job_always_starts_even_when_memory_is_scarce`.

#### Scenario: Workers leave with their parent
- **WHEN** the parent of a pool worker is gone
- **THEN** the worker exits instead of holding its memory
- Verified by `tests/test_memguard.py::test_a_worker_exits_when_its_parent_is_gone`.
