## ADDED Requirements

### Requirement: A Dry Run Says What Would Be Downloaded
`baseballpy ingest --dry-run` MUST, besides the planned jobs, report how many registered datasets and season
folders the selection covers, how many season folders the lake already holds, how many it would download, a
typical size in bytes for those from measured values (datasets without a measurement counted as unknown, never
as zero), and the names it could not resolve to registered datasets. It MUST download nothing and need no network when
seasons are given, and MUST say so when the seasons are not given and cannot be estimated.

#### Scenario: A user asks what a command would fetch
- **WHEN** a dry run is made for a source and seasons, some of which the lake already holds
- **THEN** the footer lists the held and missing season folders, a typical size for the missing ones, the unknown count, and `--json` stays one object per job
- Verified by `tests/test_ingest_estimate.py::test_held_season_folders_are_not_counted_and_unknown_datasets_are_not_zero` and `tests/test_ingest_estimate.py::test_the_dry_run_prints_the_estimate_and_json_stays_one_object_per_job`.
