# Design

- The `LahmanTable` enum values are the underscore names; Lahman's spelling is found by matching the enum to the generated table list (`UPSTREAM_NAMES`), so there is no second list of 27 names.
- `canonical_table_name` accepts any spelling (`BattingPost`, `battingpost`, `batting_post`).
- Rejected: renaming only the view (leaves two names and a special case); CamelCase everywhere (SQL ignores case; clashes with the other sources).
- Known edge: a lake migrated from layout v1 keeps CamelCase Lahman folders (`core/` must not import `sources/`); Lahman is 13 s to reload, so delete `raw/lahman` and `processed/lahman` and ingest again. On Windows a CamelCase folder also hides the difference because file names ignore case.
- Every other source already followed the rule; `tests/test_table_names.py` proves it for all 459 datasets.

## Evidence
- Lahman reloaded from scratch into the project data folder; 27 views `lahman_<underscore name>` in DuckDB.
