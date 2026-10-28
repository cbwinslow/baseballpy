# chadwick-register Specification

## Purpose
Defines the ingestion and crosswalk specifications for the Chadwick Bureau Baseball Register (People / Register), mapping player identities across all baseball databases.

## Requirements

### Requirement: Master ID Crosswalk Resolution
The system MUST download, cache, and index the Chadwick Register table to translate between:
- `key_person`: Chadwick UUID
- `key_mlbam`: MLBAM / Statcast / MLB Stats API player ID (integer)
- `key_retro`: Retrosheet player ID (8-character alphanumeric)
- `key_bbref`: Baseball-Reference ID (slug)
- `key_bbref_minors`: Baseball-Reference minor league ID
- `key_fangraphs`: FanGraphs player ID (integer)
- `key_npb`: Nippon Professional Baseball ID
- `key_wikidata`: Wikidata entity ID

The system MUST provide a `PlayerIdType` enum and `crosswalk(id_val, from_type, to_type)` helper.

#### Scenario: Translating MLBAM ID to Retrosheet ID
- **GIVEN** an MLBAM player ID `660271` (Shohei Ohtani)
- **WHEN** resolved via `register.resolve_id(660271, PlayerIdType.MLBAM, PlayerIdType.RETRO)`
- **THEN** returns `"ohtas001"`.
- Verified by `tests/test_chadwick.py::test_chadwick_register_lookups_and_crosswalk`.

### Requirement: Discovery and Completeness
Shard and auxiliary files MUST be discovered from the repository git tree at the pinned ref (`people-0.csv` … `people-f.csv`, `names.csv`, `links.csv`, `countries.csv`); a missing shard is a hard error; files in `data/` that no dataset covers are logged as coverage gaps; unknown columns are preserved in `_extras`. The register MUST be compiled into the datasets `register`, `register_names`, `register_links` and `register_countries` with strict schemas generated from the real headers.

#### Scenario: Missing shard
- **GIVEN** a tree that lacks `people-7.csv`
- **WHEN** the register is extracted
- **THEN** an error naming the shard is raised and nothing is recorded as completed.
- Verified by `tests/test_chadwick_coverage.py::test_missing_shard_in_tree_is_a_hard_error` and `tests/test_sources_hardening.py::test_chadwick_missing_shard_is_hard_error`.

### Requirement: Revalidation
A pinned ref MUST be considered current only if it was fetched at exactly that SHA; a floating ref MUST be revalidated against the upstream SHA at least every 24 hours. SHA lookup failures MUST be logged and surfaced, never silently ignored, and GitHub API calls MUST send `GITHUB_TOKEN` when it is set.

#### Scenario: Pinned ref needs no API call, floating ref revalidates
- **WHEN** a ref is pinned and was fetched at that SHA
- **THEN** no GitHub API call is made; a floating ref is revalidated after the TTL and refetched when the SHA changed
- Verified by `tests/test_sources_hardening.py::test_chadwick_pinned_ref_needs_no_api_call_and_records_source_ref and ::test_chadwick_revalidates_sha_after_ttl_and_refetches_on_change`.

#### Scenario: SHA lookup failure is logged and token is sent
- **WHEN** the SHA lookup fails
- **THEN** the failure is logged (and the cached copy served), and API calls carry `GITHUB_TOKEN` when it is set
- Verified by `tests/test_sources_hardening.py::test_chadwick_sha_failure_is_logged_and_cache_served and tests/test_chadwick_coverage.py::test_tree_listing_is_cached_in_http_cache_and_token_is_sent`.

### Requirement: Nickname and Fuzzy Name Search
The system MUST index `names.csv` and nickname variants so searching informal names (e.g., "Pete Alonso") resolves formal records ("Peter Alonso"), and fuzzy search (`fuzzy=True`) tolerates spelling typos.

#### Scenario: Typo resolves with fuzzy search
- **WHEN** `search_name("Aron Juge", fuzzy=True, min_score=0.7)` runs
- **THEN** the first result is `Aaron Judge`; alias names from `names.csv` feed the search
- Verified by `tests/test_chadwick.py::test_chadwick_register_lookups_and_crosswalk and tests/test_chadwick_coverage.py::test_load_persists_all_four_datasets_and_names_feed_alias_search`.
