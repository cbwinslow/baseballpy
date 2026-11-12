# Design: sample-compare

## 1. Evidence (2026-11-11)

- `core/stores.py`: `ProcessedStore.read_part(spec, chunk, season)` reads a chunk from a part or a compacted
  file; `LakeConfig.dataset_manifest(source, dataset, "processed"|"raw", season)` lists chunks and raw files with
  their sha256 (`manifest_key` gives `season=YYYY/<chunk>`).
- The ingest machinery builds `LakeConfig()` from the environment in many places, so a scratch download is a
  child process with `BASEBALLPY_HOME` pointing at a temporary folder: no cross-contamination.
- Prior art: pybaseball and baseballr have no equivalent (they have no stored state to compare with).

## 2. Reuse check

Registry (datasets, keys), `ProcessedStore`, manifests, `click`/`rich`; no new dependency; no dataset names in code.

## 3. Decisions

- Compare per chunk, rows sorted by the registered keys, all registered columns; the lineage column is ignored.
- A chunk the lake does not have is "missing in the lake", reported but not a failure by itself (the lake may never
  have fetched it); a differing chunk or raw file is a failure.
- The scratch home is removed unless `--keep` is given.

## 4. Tests

`tests/test_sample_compare.py`: identical lakes; one changed value; a missing chunk; a changed raw sha256;
compacted chunks compare like parts; the command reports and exits 1 on a difference (the scratch download is
replaced by a function that fills the scratch home, so no network).

## 5. As built

- `ingest/sample.py` (`compare_lakes`, `run_scratch_ingest`, `SampleReport`, `Difference`), `cli_sample.py` (the
  `verify-sample` command, registered in `cli.py`). Tests: `tests/test_sample_compare.py` (4; failing first).

**Real runs against the real lake (2026-11-11, fresh downloads into a scratch home, real network):**

| Sample | Processed chunks | Identical | Raw files | Raw identical | Result |
|---|---|---|---|---|---|
| `lahman` (27 tables) | 27 | 27 | 27 | 27 | matches |
| `chadwick` (4 datasets, 555,829 rows) | 4 | 4 | 20 | 20 | matches |
| `mlb_api -s 2024 -d teams_season` | 1 | 1 | 1 | 1 | matches |
| `mlb_api -s 2024 -d games --limit 3` | 41 | 40 | 41 | 38 | differences explained below |

The three-game MLB sample differed in four places, all of the kind the segments design already predicted (design
5b): the provider answers change over time. (1) `schedule_hydrated` season 2024: the column `broadcasts` differs
(broadcast listings are updated after a game); its raw file differs in bytes for the same reason. (2) Two
`game_feed_linescore_innings` raw files (games 744796 and 744797) differ in bytes while their processed rows are
identical. 40 of the 41 processed chunks, including every per-game boxscore, feed and play dataset of the sample,
equal the lake row for row. So: the download code gives the stored output, and where it differs the provider
changed the answer, not the code.

**More real runs and two fixes the real runs forced (2026-11-11):**

- `retrosheet -s 2024` (season and reference files): 29 of 29 processed chunks and 47 of 47 raw files identical.
- `statcast -s 2024 -d pitches` (a whole season, about 70 windows): the first run reported 78 windows as different
  because Statcast category columns are Arrow dictionaries and two downloads can order a dictionary differently;
  `_rows_differ` now compares such a column by value (test first, failing before). The second run still reported 65
  windows: a real difference. In the window 2024-07-19 to 2024-07-23, 24 pitches changed from `SL`/Slider to
  `ST`/Sweeper: Savant reclassified past pitches. Row counts and keys matched. This is recorded in
  `docs/sources/statcast.md` ("Savant revises past seasons") with the `--refresh` advice.
- The first gate run failed `tests/test_ingest_architecture.py`: `ingest/sample.py` imported `sources`. The
  registry is now registered by the command (`cli_sample.py`), not by the comparison function.
