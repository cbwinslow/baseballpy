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

### Requirement: Discovery and Completeness
Shard and auxiliary files MUST be discovered from the repository git tree at the pinned ref (`people-0.csv` … `people-f.csv`, `names.csv`, `links.csv`, `countries.csv`); a missing shard is a hard error; files in `data/` that no dataset covers are logged as coverage gaps; unknown columns are preserved in `_extras`. The register MUST be compiled into the datasets `register`, `register_names`, `register_links` and `register_countries` with strict schemas generated from the real headers.

#### Scenario: Missing shard
- **GIVEN** a tree that lacks `people-7.csv`
- **WHEN** the register is extracted
- **THEN** an error naming the shard is raised and nothing is recorded as completed.

### Requirement: Revalidation
A pinned ref MUST be considered current only if it was fetched at exactly that SHA; a floating ref MUST be revalidated against the upstream SHA at least every 24 hours. SHA lookup failures MUST be logged and surfaced, never silently ignored, and GitHub API calls MUST send `GITHUB_TOKEN` when it is set.

### Requirement: Nickname and Fuzzy Name Search
The system MUST index `names.csv` and nickname variants so searching informal names (e.g., "Pete Alonso") resolves formal records ("Peter Alonso"), and fuzzy search (`fuzzy=True`) tolerates spelling typos.
