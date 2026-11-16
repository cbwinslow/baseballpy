# Tasks: easy-downloads

- [x] 1.1 Tests first: `tests/test_backfill_options.py` (a stage's `options` reach the adapter's selection; unknown or
  non-text options are refused; seasons of a stage run newest first; the built-in plans `minors` and `minors-all` load).
  Done when the tests fail for the missing key.
- [x] 1.2 `Stage.options`, newest-first season order, built-in plans `minors` and `minors-all`.
  Done when 1.1 passes and the existing backfill and plan tests pass.
- [x] 2.1 Tests first: `tests/test_python_api.py` (`download`, `update`, `backfill` plan, run, sync the views and return
  the reports, with fake adapters; seasons as int, range text and list; a bad source is a clear error).
- [x] 2.2 `baseballpy.easy` and the exports `baseballpy.download`, `update`, `backfill`.
  Done when 2.1 passes, `mypy --strict` passes and `docs generate --check` is up to date.
- [x] 3.1 Docs: `docs/QUICKSTART.md` (the few commands and Python lines), `docs/BACKFILL.md` (the plans and what they
  cost), README; ADR 144; evidence in `design.md`; gates; archive.
