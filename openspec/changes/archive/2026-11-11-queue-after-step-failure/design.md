# Design: queue-after-step-failure

## 1. Evidence (2026-11-11)

- `.baseballpy/state/queue.json`: `games 2021` done, `last_error: after-stage step exited with 1`; `games
  2020` done, `...exited with 4294967295`; `games 2019` done, attempts 3, `...exited with 1`; `games 2018`
  done, `...exited with 1`.
- Code: `ingest/queue.py` `_Background.settle` writes only `last_error`; `_run_rounds` computes
  `report.failed` before the last step is settled (the step of the final stage is settled in `close`, after
  the report exists); the docstring of `run_queue` says the failure "does not fail the stage".
- Existing test `tests/test_queue.py::test_a_finished_stage_is_compacted_and_a_compact_failure_does_not_fail_it`
  encodes the old behaviour.

## 2. Reuse check (TOOLING.md)

No tool applies; this is a status rule inside the existing queue (`tenacity` retry machinery stays as is).
The fix reuses the existing FAILED status and the failed-round continuation instead of adding a second
retry path for after-steps.

## 3. Decision

- `settle()` sets `stage.status = FAILED` and `last_error` when the after-step exits non-zero (it runs in the
  main thread, no race).
- After the stage loop of a round, `_run_rounds` calls `background.settle()` and then adds every stage whose
  status is FAILED to `report.failed` (a stage appears once).
- A FAILED stage runs again with its download (a re-run of a finished stage only checks what is cached) and
  its after-step, in the same round after `failed_wait`, as any failed stage does.
- Rejected: a separate `after_status` field and retry counter (more state, a second path through the loop
  for the same outcome); leaving the stage done and only warning (this is the defect).

## 4. Tests

In `tests/test_queue.py`: the old test is replaced by (a) a failed after-step makes the stage failed and the
report/exit code 1; (b) with `every`, the stage runs again in the same round and becomes done when the
after-step then succeeds; (c) the after-step of the last stage is settled before the report.

## 5. As built

(filled when done)

## 6. As built and gate evidence (2026-11-11)

- `ingest/queue.py`: `_Background.settle` sets the stage to `failed`; `_run_rounds` settles after the stage loop
  and adds failed stages to `report.failed`; docstring updated. No new state fields.
- Tests: `tests/test_queue.py::test_a_failed_after_step_fails_the_stage_and_it_runs_again` and
  `::test_the_last_stages_after_step_is_settled_before_the_report` (both failed on the old code; the first
  carries a 10 s guard timer so a queue that never retries fails instead of hanging).
- Gates: pytest 1626 passed, 6 skipped; ruff check clean; ruff format 755 files unchanged; mypy --strict no
  issues in 180 files; docs generate --check up to date; openspec validate --specs 22 passed.
