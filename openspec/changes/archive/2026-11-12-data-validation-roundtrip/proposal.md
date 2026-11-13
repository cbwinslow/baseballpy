# Proposal: data-validation-roundtrip (prove that no value is lost between the provider's text and our tables)

## Why
The owner asked (2026-11-12) how we know that no data is lost by casting or wrong types, that no column is missing,
and that nothing is hidden in quarantine, for Statcast and Retrosheet first, then Lahman and Chadwick.

## What exists today
Raw bytes are checked by sha256 (`cache check`); `verify-sample` downloads a sample and compares it with the lake
(our pipeline against itself, in the registered columns); Retrosheet warns about duplicate keys and orphan ids; the
lake contract tests check the shape of a fresh download; `_extras` keeps unknown columns; uncastable cells go to
quarantine; `scripts/audit_column_types.py` finds text columns that hold numbers.

## What a prototype found (2026-11-12, raw text compared with processed cells, no change to the lake)
- Statcast leaderboards, Lahman batting, Retrosheet biofile and teams: every cell equal, no value turned into NULL,
  every raw column mapped. Quarantine: 0 rows for Statcast, Lahman and Chadwick; 19 rows for Retrosheet (the stray
  `?` and `unknown` cells of the site logs). `_extras` is empty everywhere except Retrosheet `box_games` (8,787
  games with the info fields `scorer`, `howscored`, `pitches`, `inputprogvers`, `htbf`, `fieldcon`: kept, but untyped).
- **Loss 1:** Statcast `pitches` and `pitches_minors` store 50 decimal columns as 32-bit floats (ADR line 53).
  The raw text `85.8` is stored as `85.80000305175781`, `plate_x` `-0.4576421044460543` as `-0.4576421082019806`
  (differences up to 7e-6). `release_speed == 85.8` is false for users. Float64 costs 2.5% (2024: 96.7 MB to 99.1 MB).
  MLB `box_pitching` (1 column) and `standings` (3) also use 32-bit floats.
- **Loss 2:** Chadwick `register.key_npb` is `int32`; the raw ids have leading zeros (`01405134` becomes `1405134`,
  331 rows). `infer_type_name` accepts leading-zero integers, so every generated schema may hide the same loss.

## What
1. A generic round-trip check (`baseballpy verify-roundtrip`): for every raw file with a processed chunk, compare
   every cell (integers by their text, floats by value, dates by format, text exactly), count raw rows against
   processed rows plus quarantined rows, list raw columns no schema column reads, and list NULLs that came from a
   non-empty raw cell. Offline, one pass per dataset, a sample or all files.
2. `infer_type_name` and the generators treat integers with leading zeros as text; regenerate and review.
3. Statcast pitches and the four MLB columns become float64; stored chunks are rebuilt (ADR 49).
4. `box_games` info fields become typed columns.
5. Run `verify-sample` per source and record the result.
