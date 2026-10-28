## ADDED Requirements

### Requirement: Resumable Backfill
A backfill MUST run from a plan that orders reference snapshots, then seasons ascending per source, MUST resume after interruption from the dataset manifests without re-downloading completed pieces, MUST check free disk against the estimate before starting, and MUST write a per-piece summary (rows, bytes, duration, status).

#### Scenario: A plan that does not fit is refused before anything runs
- **WHEN** the plan's estimated growth plus the free-space floor exceeds the free disk
- **THEN** the run is refused with the numbers and no job starts
- Verified by `tests/test_backfill.py::test_the_disk_preflight_refuses_a_plan_that_does_not_fit`

#### Scenario: The disk budget stops the run between batches
- **WHEN** the lake has grown by `--max-gb`, or free space falls below the floor
- **THEN** the run stops with a reason, exits 2, and running the plan again resumes
- Verified by `tests/test_backfill.py::test_max_gb_stops_the_run_after_the_batch_that_crossed_it` and `tests/test_backfill.py::test_the_run_stops_when_free_space_falls_below_the_floor`

#### Scenario: An interrupted plan resumes without re-fetching finished pieces
- **WHEN** a run is interrupted after one table and the same plan is run again
- **THEN** the finished table is served from the lake (no second download) and only the incomplete one is fetched
- Verified by `tests/test_backfill.py::test_resume_with_the_real_adapter_fetches_only_what_is_incomplete`

#### Scenario: A malformed plan is rejected with the stage that is wrong
- **WHEN** a plan has no stages, an unknown key, a reversed season range, a non-positive limit or a negative estimate
- **THEN** loading it raises an error naming the stage
- Verified by `tests/test_backfill.py::test_bad_plans_are_refused`
