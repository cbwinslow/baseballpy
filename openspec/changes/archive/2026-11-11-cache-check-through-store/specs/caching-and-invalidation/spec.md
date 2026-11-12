## ADDED Requirements

### Requirement: Cache Decisions Treat Plain And Compacted Chunks Alike
Every source MUST decide whether a chunk is already stored, and MUST read a stored chunk, through the
`ProcessedStore` (`has_part`, `is_cached`, `read_part`), never by testing for a part file name. A chunk held
by a compacted file MUST count as stored and be served without a request; a chunk whose recorded compacted
file is missing or no longer lists it MUST count as not stored and be downloaded again.

#### Scenario: A compacted Statcast season is not downloaded again
- **WHEN** a Statcast season is ingested, compacted, and ingested again
- **THEN** every window is served from the lake with no request and the same rows; with the compacted file
  removed the windows are downloaded again and give the same rows
- Verified by `tests/test_cache_through_store.py::test_a_compacted_statcast_season_is_served_from_the_lake` and `tests/test_cache_through_store.py::test_a_lost_compacted_file_makes_the_windows_parse_again_from_their_raw_files`.

#### Scenario: A chunk its compacted file lacks is not cached
- **WHEN** the records call a chunk compacted but the compacted file no longer lists it
- **THEN** the store reports it as not cached
- Verified by `tests/test_cache_through_store.py::test_a_chunk_its_compacted_file_lacks_is_not_cached`.
