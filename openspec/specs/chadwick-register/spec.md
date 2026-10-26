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

### Requirement: 16-Hex Shard Ingestion and Commit SHA Tracking
Upstream `chadwickbureau/register` distributes data across 16 hex shards (`people-0.csv` through `people-f.csv`), plus `names.csv` and `links.csv`.
The system MUST download all 16 shards, track GitHub commit SHAs to detect weekly upstream changes, and compile into a unified `pa.Table` stored in `~/.baseballpy/cache/chadwick/people.parquet`.

### Requirement: Nickname and Fuzzy Name Search
The system MUST index `names.csv` and nickname variants so searching informal names (e.g., "Pete Alonso") resolves formal records ("Peter Alonso"), and fuzzy search (`fuzzy=True`) tolerates spelling typos.
