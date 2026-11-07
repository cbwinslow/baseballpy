# Fresh install verification

## Why
The owner asked whether another user who installs the library and downloads data would hit problems with the downloads, file names, DuckDB or pyarrow. On 2026-11-07 the built wheel was installed in an empty virtual environment with an empty lake and used like a new user would: `status`, `ingest lahman chadwick`, `ingest retrosheet --seasons 1964 -d gamelogs`, `ingest statcast --seasons 2024 -d leaderboards`, `db sync`, `db views`, `catalog layout`, `cache check`, `doctor`, `export`, `baseballpy.read` and `baseballpy.sql`.

## What was found
Worked: packaged data files (plans, pinned sources), folder and file names (no odd characters, 301 files, layout clean, cache check clean), downloads (28 Lahman and Chadwick tables, 1,626 game logs, 21,442 leaderboard rows), 70 views, reads and SQL, exports verified.
Problems: (1) a catalog file written by DuckDB 2.0 (the developer machine) cannot be opened by DuckDB 1.5.6 (what a plain install resolves, because the project only requires `duckdb>=1.0.0`); (2) `backend="arrow"` was refused; (3) a missing optional pandas gave a raw traceback; (4) `ingest -d leaderboard_sprint_speed` was refused with no hint that leaderboards are fetched as the group `leaderboards`.

## What changes
A catalog from a newer DuckDB is moved aside and rebuilt (it holds only views); read-only queries explain what to run; `arrow` is accepted; a missing optional library says what to install; the unknown-dataset error explains groups.
