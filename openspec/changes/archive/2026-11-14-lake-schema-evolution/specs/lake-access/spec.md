## MODIFIED Requirements

### Requirement: Strict Views Skip The Schema Merge
Views of registered datasets MUST NOT use `union_by_name` (every part has the dataset's one strict schema); views of unregistered datasets keep it. The parts of a dataset MUST share one schema. `baseballpy db sync` MUST log a warning that names `baseballpy compact` when a registered dataset's first or last file differs from the registered schema, because a strict view takes its columns from one file.

#### Scenario: View options and part schemas
- **WHEN** view SQL is built for a registered and an unregistered dataset and a dataset with several chunks is written
- **THEN** only the unregistered view merges schemas, and all parts have equal schemas
- Verified by `tests/test_access.py::test_registered_views_skip_the_schema_merge_and_parts_share_one_schema`.

#### Scenario: A view that would hide columns is reported
- **WHEN** views are synced over a dataset whose oldest file lacks a column the registered schema has
- **THEN** a warning names `baseballpy compact`, and after the migration no warning is logged
- Verified by `tests/test_schema_evolution.py::test_sync_warns_when_a_view_would_hide_columns`.

## ADDED Requirements

### Requirement: Reads Survive Files Written Under An Older Schema
`baseballpy.read` MUST scan a registered dataset under its registered schema: a column that older files lack MUST come back as empty cells, and a column the schema does not have MUST still raise an error.

#### Scenario: Old and new files in one dataset
- **WHEN** a dataset holds an old file without a typed column and a newer file with it
- **THEN** `read` (eager and lazy) returns every row, with empty cells for the old rows
- Verified by `tests/test_schema_evolution.py::test_read_survives_old_and_new_files`.

### Requirement: Old Files Are Migrated To The Registered Schema Without Losing A Value
`baseballpy compact` MUST first rewrite every file whose columns differ from the registered schema: a value found in `_extras` under the upstream name of a new column MUST move to that column (cast with quarantine) and leave `_extras`; a file that cannot be migrated cleanly MUST be left untouched and reported; a chunk's schema fingerprint MUST be updated only when its stored fingerprint proves the schema was the only difference. Compacted files keep their chunk map.

#### Scenario: Values move out of `_extras`
- **WHEN** an old file carries `{"player.nameSlug": "x", "other": 1}` in `_extras` and the schema has `player_name_slug`
- **THEN** the column holds `x`, `_extras` holds only `{"other": 1}` (or NULL when nothing is left), and the row count is unchanged
- Verified by `tests/test_schema_evolution.py::test_promote_moves_the_value_out_of_extras`, `tests/test_schema_evolution.py::test_promote_without_a_value_leaves_the_column_empty_and_extras_alone` and `tests/test_schema_evolution.py::test_promote_emptied_extras_become_null`.

#### Scenario: Migration of a dataset
- **WHEN** a dataset with an old part file is migrated, then migrated again, and in another case a compacted file is migrated
- **THEN** old rows get their values, the chunk is certified only when its fingerprint matches the old columns, the second run rewrites nothing, and the compacted chunk map is unchanged
- Verified by `tests/test_schema_evolution.py::test_migration_fills_old_rows_and_certifies_the_chunk`, `tests/test_schema_evolution.py::test_a_chunk_that_was_stale_for_another_reason_is_not_certified`, `tests/test_schema_evolution.py::test_a_compacted_file_keeps_its_chunk_map_after_migration` and `tests/test_schema_evolution.py::test_compact_rewrites_old_files_first`.

#### Scenario: A file with an unknown column
- **WHEN** a file has a column the registered schema lacks
- **THEN** the file is left untouched and listed as failed
- Verified by `tests/test_schema_evolution.py::test_a_file_with_an_unknown_column_is_left_alone_and_reported`.
