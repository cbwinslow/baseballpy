# Tasks: queue-after-step-failure

Order: 1.1 -> 1.2 -> 1.3.

- [x] 1.1 Tests first in `tests/test_queue.py`: a failed after-step makes the stage failed (report, exit code
  1, state file); it is run again in the same round and ends done when the after-step then works; the last
  stage's after-step is settled before the report. Replace the old test that asserted the stage stays done.
  Done when the new tests fail against the current code.
- [x] 1.2 `ingest/queue.py`: `settle()` marks the stage failed; `_run_rounds` settles after the stage loop and
  lists failed stages; update the `run_queue` docstring.
  Done when 1.1 passes and the rest of `tests/test_queue.py` still passes.
- [x] 1.3 Records and gates: spec requirement in `cli-and-ingest`, ADR 101, tick product-mandate task 2.3
  (B-410), gates (pytest, ruff, format, mypy, docs, openspec validate), archive.
  Done when evidence is in `design.md` and the change is archived.
