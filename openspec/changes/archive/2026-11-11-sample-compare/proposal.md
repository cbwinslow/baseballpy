# Proposal: `baseballpy verify-sample`, the sample comparison

## Why

ADR 108 lets old data be backed up and downloaded again, with a small sample downloaded and compared first.
AGENTS.md section 15 rule 5 asks for a rebuild check per source (B-408). Today nothing downloads a sample and
compares it with the lake: the contract tests use recorded fixtures, and the real lake is only checked by
`cache check` (the files against their own recorded checksums).

## What

- `baseballpy/ingest/sample.py::compare_lakes(sample, lake, sources)`: for every completed processed chunk of the
  sample lake, find the same chunk in the lake and say identical, rows differ (with the first differing column),
  or missing in the lake; for every raw file of the sample, compare its sha256 with the lake's record
  (identical, bytes differ, missing). Pure and offline: it reads two lakes.
- `baseballpy verify-sample SOURCE [-s SEASONS] [-d DATASETS] [--limit N]`: runs the normal `ingest` for that
  selection into a fresh scratch home (a child process with `BASEBALLPY_HOME` set; the real lake is not touched),
  then compares the scratch home with the real lake, prints a table and exits 1 when anything differs.
- A difference is information, not always a bug: a provider answer can change over time (live feeds). The
  report says what differs and where, so it is explained in the change or fixed in code (ADR 108).

## Out of scope

Comparing segment layouts chunk by chunk (segments have no chunk keys; their comparison is the rebuild table,
`response-log-segments` 6.3); deleting or replacing anything.
