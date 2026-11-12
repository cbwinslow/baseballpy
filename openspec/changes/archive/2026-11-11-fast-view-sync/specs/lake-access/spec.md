## ADDED Requirements

### Requirement: The Inventory Reads A Parquet Footer Only For A New Or Changed File
The DuckDB inventory (`v_season_catalog`) MUST count rows from a cache of Parquet footers keyed by file path, size
and modification time, MUST open a footer only for a file that is new or changed, and MUST give the same rows with or
without the cache.

#### Scenario: A second refresh opens no footer
- **WHEN** the inventory rows are built twice and then one file is rewritten
- **THEN** the second build opens no footer and returns the same rows, and the third reads only the rewritten file and counts its new rows
- Verified by `tests/test_database.py::test_the_inventory_reads_a_file_footer_only_when_the_file_is_new_or_changed`.
