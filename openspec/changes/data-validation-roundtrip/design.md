# Design: data-validation-roundtrip

## 1. Evidence: what the check found (real lake, 2026-11-12)

`baseballpy verify-roundtrip` re-reads sampled raw files as text and compares every cell with the stored value.

| Source | Datasets | Clean | Loss | Skipped (reason) |
|---|---|---|---|---|
| Statcast | 50 | 48 | `pitches`, `pitches_minors` (50 decimal columns stored as 32-bit floats) | none |
| Lahman | 27 | 27 | none | none |
| Chadwick | 4 | 3 | `register.key_npb` (leading zeros dropped, 331 people) | none |
| Retrosheet | 43 | 28 | `umpire_logs.temp` 3 cells (the stray `unknown`, quarantined by design) | 11 (events, event-derived tables, box accounts: raw files are Chadwick event files, not CSV) |

Other findings: Retrosheet `box_games` held six info fields in `_extras` for 8,787 games; roster lines without a
position were stored as an empty string; quarantine holds 0 rows for Statcast, Lahman and Chadwick and 19 rows for
Retrosheet (the stray cells of the site logs and umpire logs).

False alarms that shaped the tool: keys that repeat (Lahman awards, game logs) need a multiset comparison; raw windows
that overlap or hold several fetched versions of a row (Statcast minors 2026) can only be checked by key coverage.

## 2. Prior art and reuse check
`verify-sample` (ADR 108) compares our pipeline with itself on a fresh download; the new check compares the pipeline
with the provider's text, which `cache check` (sha256 of raw bytes) cannot. Reused: Arrow compute, `read_csv_strings`,
the registry, the quarantine files, `schema_from_columns` metadata (upstream names, date formats).

## 3. Decisions
- Integer columns are compared by text, floats by value as 64-bit floats, dates by format, text exactly.
- A dataset the tool cannot read is `skipped` with the reason, never clean.
- The lake contract runs the check on every fresh download in the tests.
- Decimals are `float64`, identifiers text (AGENTS.md section 3B).

## 4. Tests
`tests/test_roundtrip.py` (equal cells, 32-bit float, dropped zero, NULL, missing row, unmapped column, skipped, repeated
keys and overlapping windows), `tests/test_schema_rules.py`, `tests/test_infer_types.py`, `tests/test_chadwick.py`,
`tests/test_retrosheet_box.py`, `tests/test_retrosheet.py`, and `tests/lake_contract.py` (every download test).

## 5. Provider specifications read (2026-11-12)
Savant CSV documentation: units for some fields, no types or precision; `plate_x` redefined in 2026; `vy0` listed
twice. Chadwick register README: ids described as the person's identifier on a site, no type or format. Retrosheet
event file specification: info field names, values and sentinels (documented in `docs/sources/retrosheet.md`).
