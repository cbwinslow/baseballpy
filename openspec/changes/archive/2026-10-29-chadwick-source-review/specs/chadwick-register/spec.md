## MODIFIED Requirements

### Requirement: Master ID Crosswalk Resolution
The system MUST download, cache, and index the Chadwick Register table to translate between every identifier system of `PlayerIdType`, in both directions:
- `key_person`: the short Chadwick person key (the first 8 hex digits of the UUID; unique within one release, but upstream may re-use it for a different identity over time)
- `key_uuid`: the Chadwick UUID and primary key (never re-used)
- `key_mlbam`: MLBAM / Statcast / MLB Stats API player ID (integer)
- `key_retro`: Retrosheet player ID (8-character alphanumeric)
- `key_bbref`: Baseball-Reference ID (slug)
- `key_bbref_minors`: Baseball-Reference minor league ID (a different id space from `key_bbref`)
- `key_fangraphs`: FanGraphs player ID (integer)
- `key_npb`: Nippon Professional Baseball ID (integer)
- `key_wikidata`: Wikidata entity ID

The system MUST provide a `PlayerIdType` enum and `crosswalk(id_val, from_type, to_type)` helper; an unknown id type MUST raise `ValueError` and an unknown id MUST return `None`.

#### Scenario: Translating MLBAM ID to Retrosheet ID
- **GIVEN** an MLBAM player ID `660271` (Shohei Ohtani)
- **WHEN** resolved via `register.resolve_id(660271, PlayerIdType.MLBAM, PlayerIdType.RETRO)`
- **THEN** returns `"ohtas001"`.
- Verified by `tests/test_chadwick.py::test_chadwick_register_lookups_and_crosswalk`.

#### Scenario: Every id type crosswalks both ways and minors ids are their own space
- **GIVEN** a register row that has all nine ids
- **WHEN** each id type is resolved to every other type
- **THEN** each result is the target column of that row, and MLBAM `660271` to `PlayerIdType.BBREF_MINORS` is `"otani-000sho"` (not the `key_bbref` value)
- Verified by `tests/test_chadwick.py::test_resolve_id_round_trips_every_id_type_in_both_directions` and `tests/test_chadwick.py::test_resolve_id_bbref_minors_is_not_confused_with_bbref`.

#### Scenario: Unknown types and ids
- **WHEN** `resolve_id` gets an unknown id type or an id that is not in the register
- **THEN** the unknown type raises `ValueError` and the unknown id returns `None`
- Verified by `tests/test_chadwick.py::test_resolve_id_rejects_unknown_id_types` and `tests/test_chadwick.py::test_resolve_id_accepts_names_ignores_case_and_returns_none_for_unknown_ids`.

## ADDED Requirements

### Requirement: Per-Dataset Ingest Without the Lookup Index
Every registered Chadwick dataset (`register`, `register_names`, `register_links`, `register_countries`) MUST be selectable for ingest by name, the dataset names MUST come from the dataset registry, one ingest MUST download the upstream files once, an ingest MUST NOT build the in-memory lookup index, and a job MUST report the rows of each dataset it handled. The upstream `README.md` MUST be kept in `raw/chadwick/register/` with its sha256 whenever the git tree lists it.

#### Scenario: Selecting one dataset
- **WHEN** `baseballpy ingest chadwick -d register_names` runs
- **THEN** only `register_names` is typed and stored, a second run downloads nothing, and an unknown name is rejected with the registry's names
- Verified by `tests/test_chadwick_coverage.py::test_ingest_subset_reuses_the_cache_and_unknown_names_fail` and `tests/test_ingest_adapters.py::test_chadwick_adapter`.

#### Scenario: Ingest stores every dataset and builds no index
- **WHEN** the default ingest runs
- **THEN** all four datasets are stored with their row counts and the lookup index is never constructed
- Verified by `tests/test_chadwick_coverage.py::test_ingest_stores_all_datasets_without_building_the_lookup_index` and `tests/test_chadwick_coverage.py::test_ingest_has_a_parser_for_exactly_the_registered_datasets`.

#### Scenario: Upstream README is kept
- **GIVEN** a git tree that lists `README.md`
- **WHEN** the register is extracted
- **THEN** the README is stored under `raw/` with a verifiable sha256 and is not downloaded again on a cached run
- Verified by `tests/test_chadwick_coverage.py::test_upstream_readme_is_kept_with_its_sha256_when_the_tree_lists_it`.

### Requirement: Lazy Lookup and Data-Driven Name Search
Constructing a register MUST build no index; each id index MUST be built on first use from the non-null values and a repeated id MUST be logged with the first row winning. Nickname variants of a first name MUST be learned from the register (people whose `name_first` differs from the first word of `name_given`), with a short fallback list for what the data cannot show; a person's own `name_nick` and the `names.csv` spellings MUST resolve as aliases; fuzzy search MUST rank by Jaro-Winkler similarity through the shared similarity helper.

#### Scenario: Nicknames are learned from the data and noise is dropped
- **GIVEN** a register where many people are "Mike" with given name "Michael" and one is "Mike" with given name "George"
- **WHEN** the nickname table is learned
- **THEN** "mike" maps to "michael" only, and the fallback list still adds its diminutives
- Verified by `tests/test_chadwick.py::test_nicknames_are_learned_from_the_register_and_noise_is_dropped` and `tests/test_chadwick.py::test_search_uses_nicknames_learned_from_the_register_data`.

#### Scenario: Own nickname and fuzzy matches
- **WHEN** "Babe Ruth" is searched and the register has name_nick "Babe" for George Ruth, and "Aron Juge" is searched with `fuzzy=True`
- **THEN** George Ruth is found by alias and Aaron Judge is the first fuzzy match
- Verified by `tests/test_chadwick.py::test_search_finds_a_person_by_their_own_nickname` and `tests/test_chadwick.py::test_fuzzy_search_ranks_the_closest_name_first`.

#### Scenario: Nothing is indexed up front
- **WHEN** a register is constructed and then an id that appears twice is resolved
- **THEN** no index existed before the lookup, a warning names the repeated column, and the first row is returned
- Verified by `tests/test_chadwick.py::test_register_builds_nothing_up_front_and_warns_about_repeated_ids`.
