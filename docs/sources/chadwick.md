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
- **Keys (from the upstream README):** `key_uuid` is the primary key and is never re-used. `key_person` is the first 8 hex digits of it: unique within one release, but upstream may re-use a short key for a different identity over time. `names` and `links` refer to people by `key_person`, so join them only against the register of the same release. The upstream README is kept at `raw/chadwick/register/README.md` (with its sha256).
- `key_bbref_minors` is filled for every person (it is not limited to minor leaguers) and is a different id space from `key_bbref`; `key_npb` is an integer.
- Upstream quirks (verified 2026-10-29 on the pinned commit): `links.source` holds `tsncardS` (capital S) on a few rows besides `tsncards`; one `names.csv` row names a `key_person` that is not in the register. Both are kept as published.
- Selecting data: any of the four datasets can be ingested by name (`baseballpy ingest chadwick -d register_names`); one ingest downloads the files once and reports the rows of each dataset.
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
reg.resolve_id(660271, PlayerIdType.MLBAM, PlayerIdType.RETRO)  # -> "ohtas001"

# 3. Complete record lookup
player = reg.resolve(mlbam=660271)

# 4. Name search: exact name, aliases (names.csv spellings and each person's own nickname), nickname
#    variants learned from the register ("Michael Trout" finds Mike Trout), then substring
reg.search_name("Mike Trout")

# 5. Fuzzy matching with typo tolerance (Jaro-Winkler, 10 best; default min_score 0.9)
reg.search_name("Aron Juge", fuzzy=True, min_score=0.7)
```

## Dataset reference (generated)

<!-- BEGIN GENERATED:chadwick.description_sources -->
### Description sources

- `chadwick_readme`: https://raw.githubusercontent.com/chadwickbureau/register/master/README.md

<!-- END GENERATED:chadwick.description_sources -->

<!-- BEGIN GENERATED:chadwick.register -->
### Dataset: register

Master player-ID crosswalk (data/people-*.csv shards).

- **View:** `chadwick_register`
- **Processed path:** `processed/chadwick/register/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `key_person`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `key_person` | string | yes | — | The first eight (hex) digits of the key_uuid; unique at any given time, but over time the same short key may be re-used for a different identity. (src: chadwick_readme) |
| `key_uuid` | string | yes | — | The primary key. This is guaranteed not to be re-used to label a different identity. (src: chadwick_readme) |
| `key_mlbam` | int32 | yes | — | The person's identifier at MLBAM. (src: chadwick_readme) |
| `key_retro` | string | yes | — | The person's Retrosheet identifier. (src: chadwick_readme) |
| `key_bbref` | string | yes | — | The person's identifier on Major League pages on baseball-reference.com. (src: chadwick_readme) |
| `key_bbref_minors` | string | yes | — | The person's identifier on minor league pages on baseball-reference.com. (src: chadwick_readme) |
| `key_fangraphs` | int32 | yes | — | The person's identifier on fangraphs.com. (src: chadwick_readme) |
| `key_npb` | int32 | yes | — | The person's identifier on the NPB official site, npb.or.jp. (src: chadwick_readme) |
| `key_sr_nfl` | string | yes | — | The person's identifier on pro-football-reference.com. (src: chadwick_readme) |
| `key_sr_nba` | string | yes | — | The person's identifier on basketball-reference.com. (src: chadwick_readme) |
| `key_sr_nhl` | string | yes | — | The person's identifier on hockey-reference.com. (src: chadwick_readme) |
| `key_wikidata` | string | yes | — | The person's identifier on wikidata.org. (src: chadwick_readme) |
| `name_last` | string | yes | — | Basic name component or date of birth/death (README: People files). (src: chadwick_readme) |
| `name_first` | string | yes | — | Basic name component or date of birth/death (README: People files). (src: chadwick_readme) |
| `name_given` | string | yes | — | Basic name component or date of birth/death (README: People files). (src: chadwick_readme) |
| `name_suffix` | string | yes | — | TODO |
| `name_matrilineal` | string | yes | — | TODO |
| `name_nick` | string | yes | — | TODO |
| `birth_year` | int16 | yes | — | Basic name component or date of birth/death (README: People files). (src: chadwick_readme) |
| `birth_month` | int16 | yes | — | Basic name component or date of birth/death (README: People files). (src: chadwick_readme) |
| `birth_day` | int16 | yes | — | Basic name component or date of birth/death (README: People files). (src: chadwick_readme) |
| `death_year` | int16 | yes | — | Basic name component or date of birth/death (README: People files). (src: chadwick_readme) |
| `death_month` | int16 | yes | — | Basic name component or date of birth/death (README: People files). (src: chadwick_readme) |
| `death_day` | int16 | yes | — | Basic name component or date of birth/death (README: People files). (src: chadwick_readme) |
| `pro_played_first` | int16 | yes | — | First year spanned as player in professional leagues overall (README: year spans for playing, managing and umpiring; may be incomplete). (src: chadwick_readme) |
| `pro_played_last` | int16 | yes | — | Last year spanned as player in professional leagues overall (README: year spans for playing, managing and umpiring; may be incomplete). (src: chadwick_readme) |
| `mlb_played_first` | int16 | yes | — | First year spanned as player in Major League Baseball (README: year spans for playing, managing and umpiring; may be incomplete). (src: chadwick_readme) |
| `mlb_played_last` | int16 | yes | — | Last year spanned as player in Major League Baseball (README: year spans for playing, managing and umpiring; may be incomplete). (src: chadwick_readme) |
| `col_played_first` | int16 | yes | — | First year spanned as player in intercollegiate play (README: year spans for playing, managing and umpiring; may be incomplete). (src: chadwick_readme) |
| `col_played_last` | int16 | yes | — | Last year spanned as player in intercollegiate play (README: year spans for playing, managing and umpiring; may be incomplete). (src: chadwick_readme) |
| `pro_managed_first` | int16 | yes | — | First year spanned as manager in professional leagues overall (README: year spans for playing, managing and umpiring; may be incomplete). (src: chadwick_readme) |
| `pro_managed_last` | int16 | yes | — | Last year spanned as manager in professional leagues overall (README: year spans for playing, managing and umpiring; may be incomplete). (src: chadwick_readme) |
| `mlb_managed_first` | int16 | yes | — | First year spanned as manager in Major League Baseball (README: year spans for playing, managing and umpiring; may be incomplete). (src: chadwick_readme) |
| `mlb_managed_last` | int16 | yes | — | Last year spanned as manager in Major League Baseball (README: year spans for playing, managing and umpiring; may be incomplete). (src: chadwick_readme) |
| `col_managed_first` | int16 | yes | — | First year spanned as manager in intercollegiate play (README: year spans for playing, managing and umpiring; may be incomplete). (src: chadwick_readme) |
| `col_managed_last` | int16 | yes | — | Last year spanned as manager in intercollegiate play (README: year spans for playing, managing and umpiring; may be incomplete). (src: chadwick_readme) |
| `pro_umpired_first` | int16 | yes | — | First year spanned as umpirer in professional leagues overall (README: year spans for playing, managing and umpiring; may be incomplete). (src: chadwick_readme) |
| `pro_umpired_last` | int16 | yes | — | Last year spanned as umpirer in professional leagues overall (README: year spans for playing, managing and umpiring; may be incomplete). (src: chadwick_readme) |
| `mlb_umpired_first` | int16 | yes | — | First year spanned as umpirer in Major League Baseball (README: year spans for playing, managing and umpiring; may be incomplete). (src: chadwick_readme) |
| `mlb_umpired_last` | int16 | yes | — | Last year spanned as umpirer in Major League Baseball (README: year spans for playing, managing and umpiring; may be incomplete). (src: chadwick_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `key_iso_alpha2` | string | yes | — | TODO |
| `key_iso_alpha3` | string | yes | — | TODO |
| `key_ioc` | string | yes | — | TODO |
| `key_fifa` | string | yes | — | TODO |
| `name_full_en` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `key_person` | string | yes | — | The first eight (hex) digits of the key_uuid; unique at any given time, but over time the same short key may be re-used for a different identity. (src: chadwick_readme) |
| `source` | string | yes | — | TODO |
| `value` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `key_person` | string | yes | — | The first eight (hex) digits of the key_uuid; unique at any given time, but over time the same short key may be re-used for a different identity. (src: chadwick_readme) |
| `name_last` | string | yes | — | Basic name component or date of birth/death (README: People files). (src: chadwick_readme) |
| `name_first` | string | yes | — | Basic name component or date of birth/death (README: People files). (src: chadwick_readme) |
| `name_given` | string | yes | — | Basic name component or date of birth/death (README: People files). (src: chadwick_readme) |
| `birth_year` | int16 | yes | — | Basic name component or date of birth/death (README: People files). (src: chadwick_readme) |
| `birth_month` | int16 | yes | — | Basic name component or date of birth/death (README: People files). (src: chadwick_readme) |
| `birth_day` | int16 | yes | — | Basic name component or date of birth/death (README: People files). (src: chadwick_readme) |
| `altname_type` | string | yes | — | TODO |
| `altname_lang` | string | yes | — | TODO |
| `altname_last` | string | yes | — | TODO |
| `altname_first` | string | yes | — | TODO |
| `altname_given` | string | yes | — | TODO |
| `altname_matrilineal` | string | yes | — | TODO |
| `altname_nick` | string | yes | — | TODO |
| `altname_date_start` | int16 | yes | — | TODO |
| `altname_date_end` | int16 | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:chadwick.register_names -->
