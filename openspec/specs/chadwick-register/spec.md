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
- `key_fangraphs`: FanGraphs player ID (integer)
- `key_lahman`: Lahman database player ID (`playerID`)

#### Scenario: Translating MLBAM ID to Retrosheet ID
- **GIVEN** an MLBAM player ID `660271` (Shohei Ohtani)
- **WHEN** resolved via `PlayerRegister.resolve(mlbam_id=660271)`
- **THEN** returns complete crosswalk identifiers including `key_retro="ohtas001"`, `key_bbref="ohtansh01"`, and birth date metadata.

### Requirement: Local Parquet Caching
The system MUST cache the Chadwick register locally as an indexed Parquet file, refreshing only when remote SHA changes or when explicitly flagged.
