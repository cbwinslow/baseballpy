# Design: dry-run-estimate

## 1. Evidence (2026-11-11)

- `cli_ingest._print_dry_run` prints a four-column table and the job count only.
- The registry already knows each dataset's ingest mode (`default`, `opt_in`, `on_demand`, `api_only`) and
  partition (`DatasetSpec`), `catalog status` already compares the registry with the lake, and
  `database._season_catalog_rows` already measures bytes per season folder from the Parquet files.
- Planning never needs the network when seasons are given (`tests/test_ingest_contract.py`).

## 2. Prior art and reuse check

- pybaseball and baseballr give no pre-run size or held check (searched 2026-11-11, see download-lake-contract).
  `dlt` pipelines report load info after a run only.
- Reuse: registry, `database` season-folder measurement (shared helper), `rich` table, `click`. No new
  dependency. Registry/data driven: the sizes are data (a generated JSON), the code names no dataset.

## 3. Decisions

- Measured, generated, never hand-typed or guessed; absent means unknown.
- Held means a season folder with at least one Parquet file; a partly held season counts as held (the run
  resumes it).
- The estimate is a typical size (the median of measured seasons), labelled as such with the measurement date.
- `--json` output stays one object per job; the summary is one extra final object `{"summary": {...}}` only
  with `--dry-run --json`.

## 4. Tests

`tests/test_ingest_estimate.py`: a fake sizes table and a tmp lake: held folders are not counted, unknown
datasets are counted unknown, partitioned and unpartitioned datasets, explicit dataset filter, empty seasons.
CLI: the dry-run prints the footer and the JSON summary.

## 5. As built

- `ingest/estimate.py` (`estimate`, `TypicalSize`, `load_typical_sizes`); `cli_ingest.py`: `_selections` split out of
  `_plan_all`, `_print_dry_run` prints the Estimate footer; `--json` stays one object per job.
- `scripts/measure_dataset_sizes.py` and `core/typical_sizes.json` (255 datasets measured on the owner's lake,
  2026-11-11; for example `statcast.pitches` 81.5 MB per season over 19 seasons).
- Tests: `tests/test_ingest_estimate.py` (5; failed first for the missing module).
- Real runs: `ingest statcast -s 2024 -d pitches --dry-run` on an empty home prints "1 dataset(s), 1 season
  folder(s): 0 already held, 1 to download; about 81.5 MB"; on the real lake "110 already held, 0 to
  download"; `mlb_api -d games` lists `games` as fetched as a group, not estimated.
- Deviations from the proposal: the source rate limits were dropped (no source-to-host mapping in the registry), and the `--json` summary object was dropped because `tests/test_cli_ingest.py::test_dry_run_json_output_parses_line_by_line` (an existing contract: one object per job) failed with it; the estimate is a table footer and a Python function.
