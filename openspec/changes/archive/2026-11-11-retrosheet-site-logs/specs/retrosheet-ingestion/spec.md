## ADDED Requirements

### Requirement: Player, Manager And Umpire Logs Are Tables
The Retrosheet player (batting, fielding, pitching), manager and umpire logs MUST be ingestible as opt-in typed
datasets through the `site` unit: every member file of a kind becomes rows of one table, streamed in batches, an
umpire log row MUST carry the umpire id taken from its file name, and columns the schema does not know MUST be kept
in `_extras`.

#### Scenario: Members become one typed table
- **WHEN** a zip of log files with two members per kind is ingested
- **THEN** one table per kind holds every row of every member with the registered types, the umpire id comes from the file name, and an unknown column is kept in `_extras`
- Verified by `tests/test_retrosheet_site_logs.py::test_members_become_one_typed_table_per_kind`.

#### Scenario: Batches, end to end and a current rerun
- **WHEN** members are read one per batch, and the logs are ingested twice with the network blocked
- **THEN** the batches add up to the same rows, the Parquet is written with the registered schema, and the second run finds every dataset current
- Verified by `tests/test_retrosheet_site_logs.py::test_batches_add_up_to_the_same_rows` and `tests/test_retrosheet_site_logs.py::test_logs_ingest_end_to_end_then_skip`.
