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

## As built: tasks 5.1, 5.2 and 5.6 (cards C-09, C-10, C-14), 2026-10-29
- New `sources/chadwick/ingest.py`: `ingest(datasets, refresh=...)` downloads once, types and stores the selected datasets and returns rows per dataset; cached datasets are read from the Parquet footer. Dataset names come from the registry (`dataset_names()`); a small parser table must match the registry (test). `ChadwickRegister.load` now calls it and then builds the index.
- Deviation from card C-10 (one job per dataset): the adapter keeps ONE job `register` with an optional `datasets=a,b` parameter. Reason: per-dataset jobs would each pass `--refresh` to the shared download (the same 70 MB four times, and a race when jobs run in threads). Rows are summed in `JobResult.rows`; the per-dataset counts are in `detail`.
- Missing aux file in the download: logged warning, dataset skipped with 0 rows (as before, but no longer silent).
- README: `_fetch_documents` keeps `README.md` in `raw/chadwick/register/` with sha256 when the git tree lists it; a failed download is logged and does not block the data. Cached runs fetch it only if missing.
- Spec delta written (`specs/chadwick-register/spec.md`: modified crosswalk requirement, new per-dataset ingest requirement); merged at archive (task 4.1). Docs: keys, quirks and selection added to `docs/sources/chadwick.md`.
- Real run, this PC, 2026-10-29: `ingest chadwick` job 15.3 s -> 1.8 s (download cached), cached rerun 0.05 s; `-d register_names` works; unknown names are rejected with the registry list.

## As built: tasks 5.4 and 5.5 (cards C-12, C-13), 2026-10-29
Owner chose "data-driven nicknames with a small fallback".
- `ChadwickRegister` no longer builds anything up front. Each id index is built on first use from the non-null values with Arrow (`pc.indices_nonzero`, `pc.filter`, `to_pylist` only over non-null ids); a repeated id logs a warning and the first row wins. Name search is vectorised Polars (`concat_str`, `eq`, `str.contains`); `PlayerRecord` is built on demand from a row.
- Nicknames: `sources/chadwick/search.py::learn_nicknames` counts `(name_first, first word of name_given)` pairs over the register (at least 5 people and at least 10% of the most common long form for that short name), both directions. A 24-entry `FALLBACK_NICKNAMES` covers small registers and rare diminutives. Learned pairs on the real register reproduce 76 of the 88 old hand-typed pairs; one-off famous nicknames (Babe, Chipper, Buster) now come from each person's own `name_nick` through the alias index, together with the `names.csv` spellings.
- Fuzzy search: new `core/similarity.py::top_matches` (DuckDB `jaro_winkler_similarity`; sources reach DuckDB only through `core`, which keeps `tests/test_architecture.py` intact). Jaro-Winkler scores are higher than the old difflib ratio, so the default `min_score` is now 0.9 (measured on the real register: 0.9 gives 2 / 1 / 61 / 6 hits for four typo queries; 0.8 gave 215 / 86 / 416 / 105).
- Merged in edits that arrived in the working tree while this was in progress and were committed in `0c7a22e`: ids tolerate `None`, empty strings and float strings; `person`/`uuid` ids ignore case; `resolve` falls through to the next given id when the first is not found.
- Real register (526,894 people), this PC, old vs new on 24 fixed queries: construct 12.4 s -> instant; exact and nickname queries 0.00 s -> about 0.02 s; fuzzy 11-13 s -> 0.3 s; first crosswalk 0.05 s, then 1000 crosswalks in 0.04 s; top result identical on all queries; the one difference is the tail of the fuzzy list for "Mokie Betts" (the new score ranks different near-misses after the right person).

## S5 tests and spec gaps (task 2.1, card C-05), 2026-10-29
Added `tests/test_similarity.py` (ranking, tie-break, threshold, nulls, empty input), a Hypothesis property test (every generated MLBAM, Retrosheet and person id round-trips; Retrosheet ids ignore case), and a test for a download without `countries.csv` (warning logged, dataset 0 rows). Scenarios were added along the way (see the spec delta, merged at close). Unit tests use no network (respx and the project's socket block).

## S6 live verification (task 3.1, card C-06), 2026-10-29, this PC, empty scratch home
- `baseballpy ingest chadwick`: completed, 555,829 rows, 4.41 s (download 2.5 s); second run 0.05 s with no extract event in `audit.jsonl`.
- All 20 raw files (16 shards, 3 auxiliary files, README.md) pass `RawStore.verify` (sha256 against the manifest): this is the first real use of `verify`.
- CSV rows against processed rows: register 526,894 = 526,894; names 1,346 = 1,346; links 27,340 = 27,340; countries 249 = 249.
- Crosswalk: MLBAM 660271 to `ohtas001`, 592450 to `judga001`, 545361 to `troum001`; Ohtani minors id `otani-000sho`; "Michael Trout" finds Mike Trout (1991).
- `baseballpy db sync` registered 6 views; `catalog audit` covers only `mlb_api` and `statcast`, so Chadwick completeness is the tree inventory of S1 (all 19 data files mapped, README kept).
- Finding: the audit event of a cached rerun says `cache_hit=False` (the ingest job does not report that it skipped the work). Added as task 2.4 of `data-workflow-standard`.

## S7 export, docs, close (tasks 3.2 and 4.1, cards C-07 and C-08), 2026-10-29
Every dataset written through each existing sink and read back (rows, column names, types, equality):
| Sink | register (526,894 rows) | names | links | countries |
|---|---|---|---|---|
| `ParquetSink` | identical, 1.2 s | identical | identical | identical |
| `DuckDBSink` | identical, 3.1 s | identical | identical | identical |
| `PolarsSink` | identical, 0.03 s | identical | identical | identical |
| `DltSink` to DuckDB | only `register_countries` tried: 249 rows, 6 columns, all VARCHAR | not tried | not tried | |
| CSV | no project sink (pyarrow `write_csv` works as a one-liner) | | | |
Gaps for Track 6a (export command, ADR 44): no CSV sink, no PostgreSQL path from the CLI (`DltSink` in Python only), the CLI exposes only the DuckDB and Parquet sinks, the larger datasets were not pushed through `dlt`. Fingerprint for the kept README (blob SHA) waits for `data-workflow-standard` 2.1.
Close: ADR 45 written, spec delta merged into `openspec/specs/chadwick-register/spec.md` (6 requirements, 13 scenarios, all citing tests), `docs/sources/chadwick.md` updated, change archived.
