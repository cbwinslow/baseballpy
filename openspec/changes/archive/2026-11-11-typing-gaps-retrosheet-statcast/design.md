# Design: typing-gaps-retrosheet-statcast

## 1. Evidence

Audit of the real lake on 2026-11-11 (`scripts/audit_column_types.py`: DuckDB `TRY_CAST` over every string column of
every Retrosheet and Statcast view). Before: 27 text columns looked typed, 22 without a recorded reason (all Statcast
leaderboards). After the fixes and the re-download: 5 remain, all with a recorded reason, 0 without.

## 2. Prior art and reuse check

- `core/schema_tools.infer_type_name` already infers a type from string cells; it is reused. The only change is in the
  generator: a season with no value at all for a column gives no type evidence (`observed_type` returns `None`), so an
  empty season cannot widen the column to text. Savant returns some columns completely empty for 2008-2015.
- The audit uses DuckDB (`TRY_CAST`, `TRY_STRPTIME`) over a sample, not hand-written parsers.
- Retrosheet dates reuse the project's coercion (`to_date`, bad values quarantined, never dropped).

## 3. Decisions

- The generator probes every season from `FIRST_SEASON` to the current year (`probe_years`); no hard-coded season list.
- Columns stay text on purpose only with a recorded reason (`KNOWN_TEXT` in the audit): play text, line scores,
  partial dates (year only), `makeup_date` with free text.
- A schema change makes stored chunks stale (ADR 49); the datasets are downloaded or rebuilt from raw again.

## 4. Tests

`tests/test_typing_audit.py` (probe seasons come from the data not a list; text columns holding only numbers or dates
are found while leading zeros and mixed text stay text; an empty season gives no type evidence), plus the Retrosheet
parser tests for date32 daily splits and the int16 tiebreaker.

## 5. As built (real runs, 2026-11-11)

- Regenerated the 36 leaderboard schemas live: no column lost, 2 added (`outs_above_average` lateral toward 1B and 3B
  line), 22 columns changed from `string` to `float64` or `int16`. Text-typed leaderboard columns: 109 to 87 in the
  registry module overall.
- Re-downloaded all leaderboards for 2008-2026 (19 season jobs, about 3 minutes of downloading) and re-ran the audit:
  no Statcast column is text that holds only numbers or dates.
- Retrosheet `daily_splits` and `box_games` rebuilt offline from raw.
