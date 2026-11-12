# Proposal: close the typing gaps found by the Retrosheet and Statcast audit

## Why

The owner asked (2026-11-11) to wrap up Retrosheet and Statcast: every dataset strongly typed, nothing dropped,
a clean download. A data-driven audit of the real lake (`audit` below) found where a column is typed `string` but
holds typed data. Nothing is lost (the text is stored), but the types are wrong, which breaks sums, sorts and
joins for users (AGENTS.md section 3: strongly typed, never untyped text).

## Evidence (2026-11-11, real lake, DuckDB `TRY_CAST` over every string column of every Retrosheet and Statcast view)

- No dataset uses `_extras` (0 non-null rows in all 63 datasets): every upstream column has its own typed column.
- Columns that are always empty are the provider's deprecated Statcast fields (`spin_rate_deprecated`,
  `break_angle_deprecated`, ...), kept because Savant still sends the header.
- **Statcast leaderboards, 21 columns typed `string` that hold only numbers** (every non-null value casts):
  `fielding_run_value` (`total_runs`, `inf_of_runs`, `range_runs`, `arm_runs`, `dp_runs`, `catching_runs`,
  `framing_runs`, `fielding_runs_prevented_on_rec1b`, and more), `catcher_framing.rv_tot`,
  `park_factors` (`index_hardhit`, `index_xwobacon`, `index_xbacon`), `percentile_rankings_batter` (`arm_strength`,
  `oaa`, `bat_speed`, `squared_up_rate`, `swing_length`), `pitch_arsenals` (`st_avg_speed`, `sv_avg_speed`).
  Cause: `scripts/gen_savant_schemas.py` probes a hard-coded list of 13 seasons (`SAMPLE_YEARS`, which also breaks
  the "no hard-coded seasons" rule and skips 2009-2011 and 2013-2014); a column that is empty in every probed
  season is typed `string`.
- **Retrosheet:** `daily_splits.GAME_DT` and `APPEAR_DT` are `YYYYMMDD` text in all 5,232,185 rows and every one is
  a valid date (should be `date32`, like every other date); `box_games.tiebreaker` holds only `2` (an integer).
  Left as text on purpose, with the reason recorded: `schedule.makeup_date` (111 of 14,846 values carry free text
  such as "20170911 in New York"), `reference_biofile0.birthdate`/`deathdate` (772 of 24,452 birth dates are partial),
  line scores and play text (digits with meaning as text).

## What

1. `daily_splits` dates become `date32`, parsed with the project's coercion (bad values quarantined, never dropped);
   `box_games.tiebreaker` becomes `int16`.
2. The Savant generator probes every season from `FIRST_SEASON` (`sources/statcast/seasons.py`) to the current one
   instead of a fixed list; the 36 leaderboard schemas are regenerated live and the changed types reviewed.
3. A reusable audit, `scripts/audit_column_types.py` (text columns of a lake that hold only numbers or dates),
   with a unit test, so the check is repeatable and part of the Retrosheet and Statcast "done" definition.
4. The affected datasets are downloaded or rebuilt again with the new schemas (a schema change makes stored chunks
   stale, ADR 49; Retrosheet is rebuilt offline from raw) and the audit is run again.

## Out of scope

Splitting `makeup_date` into a date and a note (a design decision for the owner); changing any other dataset.
