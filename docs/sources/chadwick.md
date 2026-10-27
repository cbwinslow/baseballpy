# Chadwick Bureau Player Register Endpoint & Schema Catalog

## Upstream Overview
- **Provider:** The Chadwick Baseball Bureau (`chadwickbureau/register`), data licensed ODC-By 1.0 (see `docs/DATA_LICENSES.md`).
- **Pinned commit:** `src/baseballpy/core/sources_lock.json` key `chadwick_register` (override with `BASEBALLPY_CHADWICK_REF`; a branch name such as `master` floats on purpose).
- **Endpoints**
  | Purpose | Method + URL |
  | --- | --- |
  | Tree discovery | `GET https://api.github.com/repos/chadwickbureau/register/git/trees/<sha>?recursive=1` (cached in `cache/http/github-tree/`; `GITHUB_TOKEN` honoured) |
  | Data files | `GET https://raw.githubusercontent.com/chadwickbureau/register/<sha>/data/<file>` |
  | Floating-ref revalidation | `GET https://api.github.com/repos/chadwickbureau/register/commits?path=data&per_page=1` (only when the ref is not a SHA) |
- **Rate limit:** 15 requests/second per host through the shared `HttpClient`; bounded concurrency 4.
- **Files discovered under `data/`** (at the current pin): `people-0.csv` … `people-f.csv` (16 shards, 526,894 people), `names.csv` (1,346 rows), `links.csv` (27,340 rows), `countries.csv` (249 rows). The monolithic `people.csv` was removed upstream.
- **Completeness:** the tree must list all 16 hex shards — a missing shard is a hard error because a partial register would silently lose players. Files in `data/` that no dataset covers are logged as coverage gaps.
- **Freshness / revalidation:** with a pinned SHA the cache is current iff it was fetched at exactly that SHA (reproducible, no API call). With a floating ref the cache is revalidated against the upstream SHA every 24 hours; a failed SHA lookup is logged and the cache is served.
- **Storage:** raw files at `raw/chadwick/register/` (shards), `raw/chadwick/register_names|register_links|register_countries/`; typed Parquet at `processed/chadwick/<dataset>/part-data.parquet`.

## Datasets
| Dataset | View | Upstream file(s) | Key |
| --- | --- | --- | --- |
| `register` | `chadwick_register` | `people-*.csv` | `key_person` |
| `register_names` | `chadwick_register_names` | `names.csv` | `key_person` + the `altname_*` columns (one upstream row is an exact duplicate) |
| `register_links` | `chadwick_register_links` | `links.csv` (`key_person, source, value`) | `key_person, source, value` |
| `register_countries` | `chadwick_register_countries` | `countries.csv` | `key_iso_alpha2` |

`v_player_crosswalk` (MLBAM ↔ Retrosheet ↔ BBRef ↔ FanGraphs ↔ Chadwick person id, plus names and MLB years) is created by `baseballpy db sync` from `chadwick_register`.

## Schema notes (verified against the real data)
- All shards share one 40-column header; schemas are **generated from the real headers** (`scripts/gen_schemas.py chadwick`) and enforced by header name, so column order never matters.
- `key_mlbam`, `key_fangraphs` and `key_npb` are integers; `key_retro`, `key_bbref`, `key_sr_*`, `key_wikidata` are text; `*_first`/`*_last` year columns are `int16`.
- `names.csv` columns are `altname_*` (not `name_*`): `altname_type`, `altname_lang`, `altname_last`, `altname_first`, `altname_given`, `altname_matrilineal`, `altname_nick`, `altname_date_start`, `altname_date_end`.
- `links.csv` identifies the external system in `source` (e.g. `tsncards`) and its identifier in `value`.
- Country code `NA` (Namibia) is data, not NULL; only empty cells are NULL.
- Any column the schema does not know is preserved as JSON in the trailing `_extras` column and logged once as `schema_drift`.

## Exhaustive Master Register Schema Dictionary (`CHADWICK_PEOPLE_SCHEMA`)
The generated dictionaries for every dataset are below (regenerate with `baseballpy docs generate`).

## Resolution API & Crosswalk Usage
```python
import baseballpy as bb
from baseballpy import PlayerIdType

# 1. Load the register (downloads the pinned shards on first use, then reads Parquet)
reg = bb.chadwick.get_register()

# 2. Crosswalk from one id system to another
reg.resolve_id(660271, PlayerIdType.MLBAM, PlayerIdType.RETRO)   # -> "ohtas001"

# 3. Complete record lookup
player = reg.resolve(mlbam=660271)

# 4. Name search including aliases and nicknames from names.csv
reg.search_name("Mike Trout")

# 5. Fuzzy matching with typo tolerance
reg.search_name("Aron Juge", fuzzy=True, min_score=0.7)
```

## Dataset reference (generated)

<!-- BEGIN GENERATED:chadwick.register -->
### Dataset: register

Master player-ID crosswalk (data/people-*.csv shards).

- **View:** `chadwick_register`
- **Processed path:** `processed/chadwick/register/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `key_person`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `key_person` | string | yes | — |  |
| `key_uuid` | string | yes | — |  |
| `key_mlbam` | int32 | yes | — |  |
| `key_retro` | string | yes | — |  |
| `key_bbref` | string | yes | — |  |
| `key_bbref_minors` | string | yes | — |  |
| `key_fangraphs` | int32 | yes | — |  |
| `key_npb` | int32 | yes | — |  |
| `key_sr_nfl` | string | yes | — |  |
| `key_sr_nba` | string | yes | — |  |
| `key_sr_nhl` | string | yes | — |  |
| `key_wikidata` | string | yes | — |  |
| `name_last` | string | yes | — |  |
| `name_first` | string | yes | — |  |
| `name_given` | string | yes | — |  |
| `name_suffix` | string | yes | — |  |
| `name_matrilineal` | string | yes | — |  |
| `name_nick` | string | yes | — |  |
| `birth_year` | int16 | yes | — |  |
| `birth_month` | int16 | yes | — |  |
| `birth_day` | int16 | yes | — |  |
| `death_year` | int16 | yes | — |  |
| `death_month` | int16 | yes | — |  |
| `death_day` | int16 | yes | — |  |
| `pro_played_first` | int16 | yes | — |  |
| `pro_played_last` | int16 | yes | — |  |
| `mlb_played_first` | int16 | yes | — |  |
| `mlb_played_last` | int16 | yes | — |  |
| `col_played_first` | int16 | yes | — |  |
| `col_played_last` | int16 | yes | — |  |
| `pro_managed_first` | int16 | yes | — |  |
| `pro_managed_last` | int16 | yes | — |  |
| `mlb_managed_first` | int16 | yes | — |  |
| `mlb_managed_last` | int16 | yes | — |  |
| `col_managed_first` | int16 | yes | — |  |
| `col_managed_last` | int16 | yes | — |  |
| `pro_umpired_first` | int16 | yes | — |  |
| `pro_umpired_last` | int16 | yes | — |  |
| `mlb_umpired_first` | int16 | yes | — |  |
| `mlb_umpired_last` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:chadwick.register -->

<!-- BEGIN GENERATED:chadwick.register_countries -->
### Dataset: register_countries

ISO / IOC / FIFA country codes (data/countries.csv).

- **View:** `chadwick_register_countries`
- **Processed path:** `processed/chadwick/register_countries/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `key_iso_alpha2`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `key_iso_alpha2` | string | yes | — |  |
| `key_iso_alpha3` | string | yes | — |  |
| `key_ioc` | string | yes | — |  |
| `key_fifa` | string | yes | — |  |
| `name_full_en` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:chadwick.register_countries -->

<!-- BEGIN GENERATED:chadwick.register_links -->
### Dataset: register_links

External player identifiers by source (data/links.csv).

- **View:** `chadwick_register_links`
- **Processed path:** `processed/chadwick/register_links/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `key_person`, `source`, `value`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `key_person` | string | yes | — |  |
| `source` | string | yes | — |  |
| `value` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:chadwick.register_links -->

<!-- BEGIN GENERATED:chadwick.register_names -->
### Dataset: register_names

Alternate names, spellings and nicknames (data/names.csv).

- **View:** `chadwick_register_names`
- **Processed path:** `processed/chadwick/register_names/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `key_person`, `altname_type`, `altname_lang`, `altname_last`, `altname_first`, `altname_given`, `altname_nick`, `altname_matrilineal`, `altname_date_start`, `altname_date_end`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `key_person` | string | yes | — |  |
| `name_last` | string | yes | — |  |
| `name_first` | string | yes | — |  |
| `name_given` | string | yes | — |  |
| `birth_year` | int16 | yes | — |  |
| `birth_month` | int16 | yes | — |  |
| `birth_day` | int16 | yes | — |  |
| `altname_type` | string | yes | — |  |
| `altname_lang` | string | yes | — |  |
| `altname_last` | string | yes | — |  |
| `altname_first` | string | yes | — |  |
| `altname_given` | string | yes | — |  |
| `altname_matrilineal` | string | yes | — |  |
| `altname_nick` | string | yes | — |  |
| `altname_date_start` | int16 | yes | — |  |
| `altname_date_end` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:chadwick.register_names -->
