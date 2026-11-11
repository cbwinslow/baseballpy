## ADDED Requirements

### Requirement: Savant Leaderboards And Retrosheet Reference Files Match The Shape
Every supported Savant leaderboard downloaded for a season, and Retrosheet's reference ingest, MUST satisfy the
same lake-shape contract as the other sources, before and after compaction.

#### Scenario: Leaderboards and reference files
- **WHEN** every supported leaderboard is downloaded for one season from its recorded page, and a Retrosheet season and its reference files are downloaded
- **THEN** the lake-shape contract holds, and holds again after compaction
- Verified by `tests/test_download_contract.py::test_every_statcast_leaderboard_download_has_the_lake_shape` and `tests/test_download_contract.py::test_a_fresh_retrosheet_download_has_the_lake_shape`.
