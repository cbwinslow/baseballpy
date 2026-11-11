## ADDED Requirements

### Requirement: A Fresh Download Has The Lake Shape
After a download into an empty home, every source MUST leave `processed/<source>/<dataset>/[season=YYYY/]`
with only `part-*`, `compact-NNNN` or `seg-NNNN` Parquet files (in a season folder exactly when the dataset
is split by season), every file with the registered column names, order and types, no folder for an
unregistered dataset, no half-written file, raw files that match their recorded sha256, and after
`baseballpy db sync` one view per dataset with data whose row count equals the rows in the files. The same
MUST hold after compaction, and a second run MUST NOT download again.

#### Scenario: Every source's download matches the shape
- **WHEN** a Statcast season, a Retrosheet season, the Chadwick register, the Lahman tables and the MLB game datasets (and every supported MLB endpoint that has a recorded answer) are downloaded from the recorded fixtures into empty homes
- **THEN** the contract holds, holds again after compaction, and a second run makes no request
- Verified by `tests/test_download_contract.py::test_a_fresh_statcast_download_has_the_lake_shape`, `tests/test_download_contract.py::test_a_fresh_retrosheet_download_has_the_lake_shape`, `tests/test_download_contract.py::test_a_fresh_chadwick_download_has_the_lake_shape`, `tests/test_download_contract.py::test_a_fresh_lahman_download_has_the_lake_shape`, `tests/test_download_contract.py::test_a_fresh_mlb_game_download_has_the_lake_shape` and `tests/test_download_contract.py::test_every_mlb_endpoint_download_has_the_lake_shape`.

#### Scenario: A dataset whose chunks are all empty keeps its view through compaction
- **WHEN** every chunk of a dataset is empty and the dataset is compacted
- **THEN** one empty file stays (the first chunk's), the chunks still count as downloaded, and the dataset's view still exists and counts zero rows
- Verified by `tests/test_compact.py::test_a_dataset_whose_chunks_are_all_empty_keeps_one_empty_file_and_its_view`.

#### Scenario: A broken lake is caught
- **WHEN** a stray file name, a wrong column type or an unregistered folder is added to a downloaded lake
- **THEN** the contract check fails
- Verified by `tests/test_download_contract.py::test_the_contract_catches_a_stray_file_a_wrong_type_and_an_unknown_folder`.
