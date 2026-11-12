# Design: retrosheet-site-logs

## 1. Evidence
Header check over every member: one distinct header per kind, no empty files. `mgr` in the manager logs is the manager
id; the umpire logs have no umpire id column (the id is in the file name).

## 2. Prior art and reuse check
Reused: `map_to_schema` (strict types, quarantine, `_extras`), `read_csv_strings`, `ProcessedStore.put_stream`,
`Fingerprint(INPUT_SET, zip sha256)`, the declarative `SITE_DATASETS` table. New: members of one zip selected by file
name suffix and read in batches (memory stays small for 1.4 GB of CSV); a vectorized type inference in the generator
(Arrow casts over whole batches, not a Python loop over cells).

## 3. Decisions
- Types come from the data: per batch int16/int32/int64/float64 else text, widened across batches; an all-empty column
  gives no evidence (ADR 109); `date` is `date32` only when every value is a valid YYYYMMDD date.
- Dataset names say what they are (no prefix); all are `opt_in`.

## 4. Tests
`tests/test_retrosheet_site_logs.py` with small fixture zips: registry, typed merge of members, filename id, extras,
batching, end-to-end write and skip, inference helper.

## 5. As built (real runs, 2026-11-11)
All eleven site datasets ingested in 211 seconds: 13,731,194 rows, every table equal to the sum of its file rows
(batting 5,771,788; fielding 5,289,957; pitching 1,274,253; manager 506,098; umpire 771,683; transactions 101,594;
biography 15,821). Findings from the real data: exact duplicate rows exist upstream (2 transactions, 7 batting, 3
umpire; kept); a few cells are not numbers in number columns (`?` once in `b_k`, `p_k`, 11 times in fielding `d_pos`;
`unknown` 3 times in umpire `temp`): those columns are declared numeric and the cells are quarantined (they stay in the
raw zip); the 28 manager-log line-score columns stay text (`x` = inning not played). The type audit then showed 0
columns without a recorded reason in Retrosheet and Statcast. The tables read back as Polars frames
(`baseballpy.read("retrosheet.manager_logs")`).
