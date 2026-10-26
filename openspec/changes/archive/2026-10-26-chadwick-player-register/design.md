# Design: Chadwick Player Register & Master Crosswalk

## Data Flow
```text
GitHub (chadwickbureau/register/data/people.csv)
                      │
     ETag / Commit SHA Check (No download if unchanged)
                      ▼
         ChadwickExtractor.extract()
                      │ (raw CSV bytes)
                      ▼
        ChadwickNormalizer.normalize()
                      │ (PyArrow Table with physical types)
                      ▼
          Local Cache Parquet Writer
          (~/.baseballpy/cache/chadwick/people.parquet)
                      │
                      ▼
               ChadwickRegister
         (In-memory hash index dictionaries)
                      │
  ┌───────────────────┼───────────────────┐
  ▼                   ▼                   ▼
resolve(mlbam=660271) resolve(retro="ohtas001") resolve(name="Shohei Ohtani")
```

## Schema Types
- `key_person`: `pa.string()` (Chadwick primary key)
- `key_uuid`: `pa.string()` (UUID4)
- `key_mlbam`: `pa.int32()` (Nullable int32 for MLBAM / Statcast)
- `key_retro`: `pa.string()` (8-character Retrosheet ID)
- `key_bbref`: `pa.string()` (Baseball-Reference slug)
- `key_fangraphs`: `pa.int32()` (Nullable int32 for FanGraphs)
- `name_last`: `pa.string()`
- `name_first`: `pa.string()`
- `name_given`: `pa.string()`
- `birth_year`: `pa.int16()`
- `birth_month`: `pa.int8()`
- `birth_day`: `pa.int8()`
- `mlb_played_first`: `pa.int16()`
- `mlb_played_last`: `pa.int16()`

## Lookup Mechanics
The `ChadwickRegister` indexes the PyArrow table into fast Python dictionary lookups:
- `_by_mlbam: dict[int, PlayerRecord]`
- `_by_retro: dict[str, PlayerRecord]`
- `_by_bbref: dict[str, PlayerRecord]`
- `_by_fangraphs: dict[int, PlayerRecord]`
- `_by_name: dict[str, list[PlayerRecord]]`
Lookups take `< 1 microsecond` with zero runtime memory bloat.
