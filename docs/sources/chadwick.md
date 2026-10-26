# Chadwick Bureau Player Register Endpoint & Schema Catalog

## Upstream Overview
- **Provider:** The Chadwick Baseball Bureau (`chadwickbureau`)
- **Base Endpoint URL:** `https://raw.githubusercontent.com/chadwickbureau/register/master/data/people.csv`
- **Method:** `GET`
- **Response Format:** CSV (Comma-Separated Values)
- **Rate Limit Policy:** Max 15 requests/second (Fastly-backed GitHub CDN)
- **Update Frequency:** Weekly / Monthly upon player debuts, roster moves, or historical discoveries.
- **baseballpy Solution:** Automatic ETag and commit hash checking. Downloads once and caches locally as indexed Parquet (`~/.baseballpy/cache/chadwick/people.parquet`) for `< 1 microsecond` lookups.

---

## Exhaustive Column & Schema Dictionary

Every column in `people.csv` is preserved and mapped to optimized PyArrow physical types:

| Column Name | PyArrow Physical Type | Nullable | Example Raw Value | Description |
| :--- | :--- | :---: | :--- | :--- |
| `key_person` | `string()` | No | `ohtas001` | Chadwick Bureau canonical human identifier (primary key) |
| `key_uuid` | `string()` | No | `8a1f81e3-4db0-4e36-932d...` | Universally unique identifier (UUIDv4) |
| `key_mlbam` | `int32()` | Yes | `660271` | Major League Baseball Advanced Media ID (Statcast / MLB API) |
| `key_retro` | `string()` | Yes | `ohtas001` | Retrosheet 8-character player identifier |
| `key_bbref` | `string()` | Yes | `ohtansh01` | Baseball-Reference player URL slug |
| `key_fangraphs`| `int32()` | Yes | `19755` | FanGraphs numeric player identifier |
| `name_last` | `string()` | No | `Ohtani` | Player legal or official surname |
| `name_first` | `string()` | No | `Shohei` | Player legal or official given name |
| `name_given` | `string()` | Yes | `Shohei` | Full legal given names |
| `birth_year` | `int16()` | Yes | `1994` | Four-digit birth year |
| `birth_month`| `int8()` | Yes | `7` | Birth month (1–12) |
| `birth_day` | `int8()` | Yes | `5` | Birth day of month (1–31) |
| `mlb_played_first` | `int16()` | Yes | `2018` | Year of official Major League debut |
| `mlb_played_last` | `int16()` | Yes | `2024` | Year of most recent Major League appearance |

---

## Resolution API Usage
```python
import baseballpy as bb

# O(1) in-memory resolution by any ID
player = bb.resolve_player(mlbam=660271)
print(player.key_retro)  # "ohtas001"
print(player.key_bbref)  # "ohtansh01"
print(player.key_fangraphs)  # 19755
```
