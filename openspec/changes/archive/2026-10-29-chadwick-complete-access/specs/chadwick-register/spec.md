## ADDED Requirements

### Requirement: Complete Data Access
Every register column MUST be readable from a `PlayerRecord` (a test keeps the record in step with the schema), and the four datasets (`register`, `register_names`, `register_links`, `register_countries`) MUST be reachable from Python: as tables, and through `names_for(person)`, `links_for(person)` and `country(code)` (ISO alpha-2/alpha-3, IOC or FIFA code, any case; `NA` is Namibia). A register built without the optional datasets MUST answer with nothing instead of failing.

#### Scenario: A record carries every column
- **WHEN** the fields of `PlayerRecord` are compared with the register schema, and a person with death dates and career spans is resolved
- **THEN** the fields equal the schema columns in order, and death dates, pro/college/MLB spans and `key_sr_*` are readable
- Verified by `tests/test_chadwick.py::test_player_record_covers_every_register_column` and `tests/test_chadwick.py::test_record_carries_death_dates_and_career_spans`.

#### Scenario: Names, links and countries from Python
- **WHEN** links, alternate names and a country code are looked up for a loaded register, and for a register built without those datasets
- **THEN** the rows of the person (or the country row) are returned, and nothing is returned for an unknown person or code and for the missing datasets
- Verified by `tests/test_chadwick.py::test_names_links_and_countries_are_reachable_from_python`.

### Requirement: Process-Wide Register Reuse
`ChadwickRegister.load` MUST keep the loaded register for the process, keyed by lake and by the time the processed register was written, and reuse it until the Chadwick time-to-live passes, a new ingest rewrites the lake, `refresh=True` or `clear_cache()`; `get_register`, `crosswalk` and `resolve_player` MUST use it so that calling them in a loop costs no further ingest.

#### Scenario: Reuse, refresh, expiry
- **WHEN** the register is loaded twice, then with `refresh=True`, from another lake, after the time-to-live, and after `clear_cache()`
- **THEN** the second load returns the same object without an ingest, and each of the other cases loads again
- Verified by `tests/test_chadwick_coverage.py::test_load_keeps_the_register_for_the_process_until_refresh_ttl_or_clear`.

#### Scenario: Helpers do not reload
- **WHEN** `crosswalk` is called six times and `resolve_player` once
- **THEN** one ingest happens
- Verified by `tests/test_chadwick_coverage.py::test_crosswalk_and_resolve_player_reuse_the_loaded_register`.
