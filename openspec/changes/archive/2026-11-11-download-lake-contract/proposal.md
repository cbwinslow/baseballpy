# Proposal: a fresh download has one shape, for every source

## Why

The owner asked (2026-11-11) for tests where new files are downloaded and the result matches the form we want,
so the download procedures can be called final. Today layout rules are checked by separate tools
(`catalog layout`, `cache check`, naming tests) but no test runs a download into an empty home and asserts
the whole shape. AGENTS.md section 15 requires the same layout for every user.

## What

- `tests/lake_contract.py`: one registry-driven helper `assert_lake_contract(config, sources)`: folder and
  file names (`part-*`, `compact-NNNN`, `seg-NNNN`; `season=YYYY` exactly when the dataset is season-split),
  column names, order and types equal to the registered schema, no unregistered folder, no half-written
  files, raw checksums ok, and one DuckDB view per dataset (name from the registry) whose count equals the
  rows in the files.
- `tests/test_download_contract.py`: per source, download with the recorded fixtures into an empty home,
  assert the contract, compact, assert it again, run again and assert nothing is downloaded; plus negative
  controls (a stray file, a wrong type and an unknown folder are caught).
- Sources are added one per task: Statcast and Retrosheet first (done in the first slice), then Chadwick,
  Lahman, MLB API (game level) and the others.
- One requirement and scenarios in `lake-access`; one ADR.

## Out of scope

Live (network) runs: they stay opt-in (`tests/live`). Changing any layout: this change only asserts it.
