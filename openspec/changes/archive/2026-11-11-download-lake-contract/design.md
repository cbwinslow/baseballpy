# Design: download-lake-contract

## 1. Evidence (2026-11-11)

- Existing pieces reused, not rewritten: `layout_audit.audit_layout` (unknown folders, mixed schemas, orphan
  compacted files), `cache_check.check_raw` (raw sha256), `BaseballDatabase.sync_views`, `core/sql.quote_ident`,
  the dataset registry, `RetroRepo`/`full_season` and the Statcast `_by_window` mock.
- First run (Statcast and Retrosheet): both pass the contract before and after compaction on the current code;
  the negative controls fail as they should.

## 1b. Prior art (web search, standard mode, 2026-11-11; AGENTS.md section 13.2)

- **pybaseball** (jldbc/pybaseball): an optional on-disk cache of each request's result (CSV or Parquet, default
  Parquet, folder set by `PYBASEBALL_CACHE`); no manifest, no raw copy, no compaction. Known trap: asking for
  future dates caches empty results (docs advise `cache.purge()`). Ours: raw kept with sha256, manifests, the
  trailing-days revalidation for the current season. Source: https://pypi.org/project/pybaseball/
- **baseball.computer / boxball** (droher): Retrosheet files go through a Rust parser into a DuckDB database
  of box-score, event and season models; the predecessor `boxball` also shipped flat-file Parquet downloads.
  Confirms the Parquet + DuckDB shape; shows the value of offering prebuilt files (a future export or release
  of snapshots). Source: https://github.com/droher/baseball.computer and
  https://dev.to/droher/boxball-prebuilt-baseball-stats-databases-using-docker-154n
- **pymlb-statsapi**: config-driven: every endpoint is generated at run time from JSON schemas (a registry),
  no hand-written model per endpoint; **python-mlb-statsapi** (zero-sum-seattle) uses hand-written Pydantic models
  per return type; **MLB-StatsAPI** (toddrob99) has plain functions plus a raw `get`. Our registry
  (`endpoints.py` plus generated schemas) is the pymlb-statsapi idea with typed Arrow columns and data kept.
  Sources: https://pymlb-statsapi.readthedocs.io/en/latest/ and https://pypi.org/project/MLB-StatsAPI/
- **baseballr / sportsdataverse**: pre-computed season files published as releases and loaded with `load_*()`;
  no local lake. Same bulk-seed idea as above (considered for MLB history, ADR 97 keeps our own raw).
  Source: https://rdrr.io/cran/baseballr/man/mlb_pbp.html
- None of them keeps raw responses with checksums, a per-dataset record of what was downloaded, or a layout
  contract; none gives the same files to every user. That is the gap this project fills, and this change tests it.

## 2. Decisions

- One helper driven by the registry, no dataset names. A source test is a download plus one call.
- The contract is the executable form of the layout promised in `docs/DATA_WORKFLOW.md` and AGENTS.md
  section 15; when `response-log-segments` changes the file names, `seg-NNNN` is already allowed and the
  helper is the place that proves the move.

## 3. As built

- `tests/lake_contract.py` (helper) and `tests/test_download_contract.py` (7 tests): Statcast, Retrosheet,
  Chadwick, Lahman, MLB game datasets, every supported MLB endpoint with a recorded answer (274 of the 356
  covered endpoints are exercised; 82 are skipped: unsupported, paginated, or needing a fan-out value the test
  does not give), and one test of the helper's negative controls.
- **The contract found one real defect** (MLB game datasets, after compaction): a dataset whose chunks are all
  empty (`game_boxscore_pitching_notes`) lost its file, so its view vanished (a query that worked before
  compaction failed after it). Fix in `core/compact.py::_drop_empty_parts`: when no chunk of a dataset has rows,
  the first chunk's empty file stays; test first in `tests/test_compact.py` (failed before the fix).
- Statcast leaderboards, the Retrosheet reference units, Kalshi, Polymarket, FanGraphs and Baseball-Reference
  are not yet under the contract (row B-433).

## 4. Gate evidence (2026-11-11)

pytest 1640 passed, 6 skipped; ruff check clean; ruff format clean; mypy --strict no issues in 180 files;
docs generate --check up to date; openspec validate --specs 22 passed. The change is closed for the five
sources and the MLB endpoints above; the remaining sources are B-433.
