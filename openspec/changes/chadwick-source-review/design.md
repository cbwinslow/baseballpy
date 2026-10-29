# Design: chadwick-source-review

Method and card format: `docs/agents/WORK_BREAKDOWN.md`; cards: `docs/agents/tracks/01-chadwick.md`.
Evidence below was produced on 2026-10-29 on the pinned commit `781c175e` of `chadwickbureau/register`
(still the latest upstream commit that day) into a scratch `BASEBALLPY_HOME`.

## S1 inventory (task 1.1, card C-01)

`fetch_tree` lists 20 blobs. Every file under `data/` is covered; only the README is not ingested.

| Upstream file | Rows | Dataset | Status |
|---|---|---|---|
| `data/people-0.csv` .. `people-f.csv` (16 x ~4.2 MB) | 526,894 | `register` | covered |
| `data/names.csv` | 1,346 | `register_names` | covered |
| `data/links.csv` | 27,340 | `register_links` | covered |
| `data/countries.csv` | 249 | `register_countries` | covered |
| `README.md` (8 KB) | | none | gap: the only upstream documentation of the id systems and key semantics is not kept (task 5.6) |

Upstream README facts that the code and spec must honour (read at the pinned SHA):
- `key_uuid` is the primary key and is never re-used; `key_person` is its first 8 hex digits, unique
  within one release but "over time the same short key may be re-used for a different identity".
- `links.csv` publishes two source systems: `tsncards` and `findagrave`.
- The public extract is updated roughly weekly; history exists since 2016.

## S2 conformance (task 1.2, card C-02): CONFIRMED defect

`baseballpy ingest chadwick -d chadwick:register_names --dry-run` (also `register_links`,
`register_countries`) fails with `unknown dataset(s) for chadwick: [...]; known: ['register']`, although
`catalog list` shows four registered Chadwick datasets. Cause: `adapter.py` `KNOWN_DATASETS = {"register"}`.
The other adapters' constants name task groups, so they are not the same defect, but only Chadwick lists
a single dataset and omits three. Second finding: `ChadwickAdapter.run` calls `ChadwickRegister.load`,
which builds the in-memory lookup index only so that `len()` can be reported; the job reports the
`register` row count (526,894) and not the other three datasets (1,346 + 27,340 + 249).

## S3 schema and types (task 1.3, card C-03)

Profiled with Polars on the processed Parquet (526,894 people). Result: the generated schema matches the data.
- Types: `key_mlbam`, `key_fangraphs`, `key_npb` are `int32` (max fangraphs 75,423,998, fits); year/month/day `int16`; no empty-string cells; `_extras` is empty (no schema drift at this pin).
- Uniqueness: no duplicate values in any of the 12 id columns, so `key_person` and `key_uuid` are both unique here and the dict indexes are safe at this pin (nothing guards a future pin).
- Null rates: mlbam 74.3%, retro 95.1%, bbref 95.4%, fangraphs 96.0%, npb 99.4%, wikidata 96.1%, sr_nfl/nba/nhl 100% (106/40/9 values).
- `key_bbref_minors` is populated for every person (0% null, 526,894 distinct), e.g. Ohtani `otani-000sho`; it is not a "minor-league only" id.
- Ranges: birth_year 1814..2011, death_year 1862..2026, mlb_played 1871..2026; no month above 12 or day above 31.
- `links.source`: `tsncards` 21,650, `findagrave` 5,682, and `tsncardS` 8 (an upstream casing variant; keep as published, document it). No duplicate (person, source, value); every link person exists in the register.
- `names.csv`: types alias 643, birth 260, alt-spelling 251, legal 191, anglicized 1; one row's `key_person` is not in the register (upstream orphan; keep, document).
- `countries.csv`: country code `NA` is data (1 row) and survives as text.
- Spec drift: `openspec/specs/chadwick-register` calls `key_person` "Chadwick UUID"; the UUID is `key_uuid`. The documented dataset key is `key_person`, the upstream primary key is `key_uuid` (task 5.6).

## S4 code review against the designated tools (task 1.4, card C-04)

Measured on this PC: read processed Parquet 2.2 s; `ChadwickRegister._build_index` 9.6 s; whole ingest
job 15.3 s (download 3.2 s); substring miss 0.2 s, fuzzy name search 11.1 s.

| Module | Finding | Verdict |
|---|---|---|
| `extractor.py` | `HttpClient`, `RawStore`, manifest, atomic writes and `ThreadPoolExecutor(max_concurrency)` are used correctly; `extract_async` is a thin `to_thread` wrapper. My suspicion of an asyncio/threads mix is refuted: the sync `HttpClient` is the project design. `extract()` returns all ~69 MB as `dict[str, bytes]`, acceptable at this size. The tree-failure fallback logs a warning and uses the known file list, acceptable (logged). | keep |
| `normalizer.py`, `schema.py`, `tables.py` | generated schemas, Arrow in and out; data check in S3 passes. | keep |
| `adapter.py` | hard-coded `KNOWN_DATASETS`; one job; builds the index to count rows; reports one dataset's rows. | fix: 5.1, 5.2 |
| `register.py` `_build_index` | 526,894-iteration Python loop over `to_pydict()` (all 40 columns converted to Python objects), 526k dataclass instances, 8 dicts; runs on every `load()`, including every ingest; a duplicate id would be silently overwritten (last wins). Arrow, Polars or DuckDB can answer id lookups from the columns directly. | migrate: 5.1, 5.4 |
| `register.py` `resolve_id` | substring tests (`"bbref" in from_str`) are wrong for `PlayerIdType.BBREF_MINORS`: MLBAM 660271 to `key_bbref_minors` returns `ohtansh01` (the `key_bbref` value; the real value is `otani-000sho`); lookups from `BBREF_MINORS`, `NPB` and `WIKIDATA` return `None` although the spec lists them. Confirmed by running it. | bug: 5.3 |
| `register.py` `PlayerRecord` | `key_npb` is annotated `str or None` but the column is `int32` (the runtime value is `int`; mypy cannot see it because `to_pydict()` is `Any`); the record carries 19 of 40 columns. | fix: 5.4 |
| `register.py` `search_name` | 70-entry hand-typed `COMMON_NICKNAMES` (includes the no-op `"shohei": ["shohei"]`) although the register has `name_nick` (3,600 distinct) and `names.csv`; substring scan and `difflib.SequenceMatcher` over 526k Python objects (fuzzy 11 s). DuckDB (a designated tool) has `jaro_winkler_similarity`; Polars has vectorised string ops. A behavior change, so it needs an owner decision. | migrate: 5.5 |
| Boundaries | `sources/chadwick` imports no database driver and no `httpx`; `tests/test_architecture.py` passes. | ok |

## Follow-up tasks created by the review
5.1 split ingest from lookup; 5.2 registry-driven adapter; 5.3 `resolve_id` explicit column map;
5.4 vectorised index, duplicate guard, `PlayerRecord` types; 5.5 data-driven nicknames and vectorised
search (owner decision); 5.6 keep the README, correct spec and docs. Cards C-09 to C-14 in the track file.

## S5 tests and spec gaps
(not started; after the fixes)

## S6 live verification
A scratch ingest on 2026-10-29 served as evidence for S3 and S4: 526,894 / 1,346 / 27,340 / 249 rows,
90 MB home, 3.2 s download, 15.3 s job. Task 3.1 repeats it clean after the fixes, including the resume run.

## S7 export, docs, close
(not started)

## As built: task 5.3 (card C-11), 2026-10-29
`resolve_id` and `resolve` now use one explicit table: every `PlayerIdType` is its own column, with its own
index in `ChadwickRegister._by_id`; int ids are coerced, retro/bbref/bbref_minors ignore case, names
(`"key_mlbam"` or `"mlbam"`) are accepted and an unknown type raises `ValueError`. Fixed the
`BBREF_MINORS` bug (MLBAM 660271 now gives `otani-000sho`) and the missing lookups from
`BBREF_MINORS`, `NPB`, `WIKIDATA`. `PlayerRecord.key_npb` is now `int | None` (was `str`). The whole
9 x 9 crosswalk matrix is a test. Targeted run: 29 passed (`test_chadwick`, `test_chadwick_coverage`,
`test_architecture`), mypy --strict clean. Duplicate-id guard and the vectorised build stay in 5.4.
