# Chadwick Bureau Player Register Endpoint & Schema Catalog

## Upstream Overview
- **Provider:** The Chadwick Baseball Bureau (`chadwickbureau/register`)
- **Base Endpoint URL:** `https://raw.githubusercontent.com/chadwickbureau/register/master/data/`
- **Method:** `GET`
- **Response Format:** Sharded CSVs across 16 hexadecimal partitions (`people-0.csv` through `people-f.csv`) + `names.csv` (nicknames and aliases) + `links.csv` (external database URLs) + `countries.csv`.
- **Note on Upstream Deprecation:** Upstream Chadwick Bureau **deprecated and removed** the monolithic `people.csv` file. `baseballpy` automatically retrieves all 16 shards, tracks GitHub commit SHAs to detect weekly upstream updates, and compiles them into a unified, strongly-typed PyArrow Table.
- **Rate Limit Policy:** Max 15 requests/second (Fastly-backed GitHub CDN).
- **Update Frequency:** Weekly upon player debuts, roster moves, or historical discoveries.
- **baseballpy Solution:** Automatic commit SHA tracking via GitHub API. Downloads all 16 shards concurrently using bounded concurrency (`Semaphore(4)`), validates them through two-phase atomic write gates (`.part`), and stores the raw shards under `~/.baseballpy/raw/chadwick/register/` and caches locally as an indexed Parquet table (`~/.baseballpy/processed/chadwick/register/part-data.parquet`) for sub-microsecond in-memory hash lookups.

---

## Shard Partitioning & File Structure

| Upstream File | Role | Records | Description |
| :--- | :--- | :---: | :--- |
| `people-0.csv` .. `people-f.csv` | Sharded Master Register | ~130,000 | 16 partitions sharded by the initial hex character of `key_uuid` |
| `names.csv` | Alternate Names & Nicknames | ~20,000 | Maps informal nicknames (e.g. Pete -> Peter), birth names, and aliases |
| `links.csv` | External Links | ~60,000 | Links `key_person` to Wikipedia, Wikidata, SABR BioProject, and BBRef |
| `countries.csv` | Country Crosswalk | ~250 | ISO alpha-2, alpha-3 codes and territories |

---

## Exhaustive Master Register Schema Dictionary (`CHADWICK_PEOPLE_SCHEMA`)

All 16 shards are normalized into a unified, strongly-typed PyArrow schema:

| Column Name | PyArrow Physical Type | Nullable | Example Raw Value | Description |
| :--- | :--- | :---: | :--- | :--- |
| `key_person` | `string()` | No | `ohtas001` | Chadwick Bureau canonical human identifier (primary key) |
| `key_uuid` | `string()` | No | `8a1f81e3-4db0-4e36-932d...` | Universally unique identifier (UUIDv4) |
| `key_mlbam` | `int32()` | Yes | `660271` | Major League Baseball Advanced Media ID (Statcast / MLB API) |
| `key_retro` | `string()` | Yes | `ohtas001` | Retrosheet 8-character player identifier |
| `key_bbref` | `string()` | Yes | `ohtansh01` | Baseball-Reference major league player slug |
| `key_bbref_minors` | `string()` | Yes | `ohtani001sho` | Baseball-Reference minor league player slug |
| `key_fangraphs` | `int32()` | Yes | `19755` | FanGraphs numeric player identifier |
| `key_npb` | `string()` | Yes | `01105137` | Nippon Professional Baseball (Japan) numeric ID |
| `key_wikidata` | `string()` | Yes | `Q248674` | Wikidata entity identifier |
| `name_last` | `string()` | No | `Ohtani` | Player legal or official surname |
| `name_first` | `string()` | No | `Shohei` | Player legal or official given name |
| `name_given` | `string()` | Yes | `Shohei` | Full legal given names |
| `name_suffix` | `string()` | Yes | `Jr.` | Name suffix (Jr., Sr., II, III) |
| `name_nick` | `string()` | Yes | `Shotime` | Common player nickname |
| `birth_year` | `int16()` | Yes | `1994` | Four-digit birth year |
| `birth_month` | `int8()` | Yes | `7` | Birth month (1–12) |
| `birth_day` | `int8()` | Yes | `5` | Birth day of month (1–31) |
| `death_year` | `int16()` | Yes | `null` | Four-digit death year (null if living) |
| `death_month` | `int8()` | Yes | `null` | Death month (1–12) |
| `death_day` | `int8()` | Yes | `null` | Death day of month (1–31) |
| `pro_played_first` | `int16()` | Yes | `2013` | Year of professional debut (including foreign/minors) |
| `pro_played_last` | `int16()` | Yes | `2025` | Year of most recent professional appearance |
| `mlb_played_first` | `int16()` | Yes | `2018` | Year of official Major League debut |
| `mlb_played_last` | `int16()` | Yes | `2025` | Year of most recent Major League appearance |

---

## Resolution API & Crosswalk Usage

```python
from baseballpy.sources.chadwick import get_register, crosswalk, PlayerIdType

# 1. Load the register (auto-downloads shards & caches as Parquet)
reg = get_register()

# 2. Fast crosswalk from one system to another using PlayerIdType Enum
retro_id = crosswalk(660271, from_type=PlayerIdType.MLBAM, to_type=PlayerIdType.RETRO)
print(retro_id)  # "ohtas001"

bbref_slug = reg.resolve_id(592450, from_type=PlayerIdType.MLBAM, to_type=PlayerIdType.BBREF)
print(bbref_slug)  # "judgeaa01"

# 3. Complete PlayerRecord lookup
player = reg.resolve(mlbam=660271)
print(player.full_name)  # "Shohei Ohtani"
print(player.key_fangraphs)  # 19755
print(player.key_uuid)  # UUID string

# 4. Nickname and alternate spelling search (powered by names.csv)
pete = reg.search_name("Pete Alonso")
print(pete[0].full_name)  # "Peter Alonso"

# 5. Fuzzy matching with typo tolerance
results = reg.search_name("Aron Juge", fuzzy=True, min_score=0.75)
print(results[0].full_name)  # "Aaron Judge"
```
