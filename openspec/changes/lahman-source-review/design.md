# Design: lahman-source-review

Method and card format: `docs/agents/WORK_BREAKDOWN.md`; cards: `docs/agents/tracks/02-lahman.md`.
Evidence goes into the sections below as each task completes (command output, counts, dates).

## Starting facts (survey before the review)
Measured 2026-10-29 (survey before the review; no code changed):
- **Datasets:** 27 Lahman tables; the `LahmanTable` enum, the generated `tables.py` and the registry all list 27; every registry key is non-empty (composite keys, up to 6 columns).
- **Upstream (`cbwinslow/lahman-database-csv`):** the pin `0377e0b8d3` is the latest commit today. The tree has 31 blobs: 27 data CSVs (42,147,792 bytes), `data/readme2025.txt` (47,976 bytes, the SABR data dictionary), `LICENSE` (22,240), `README.md` (4,369), `.gitignore` (10). Only the 27 CSVs are ingested.
- **Code:** `sources/lahman/` adapter (61 lines), extractor (182), api (244: `LahmanSource` with `get_table`, 13 named accessors, `import_archive`, `list_tables`), quality (74: stale-year warning, duplicate-key rows, orphan-player rows), schema (58), normalizer (41), generated `tables.py` (463).
- **Top-level API:** 8 functions (`batting`, `pitching`, `people`, `teams`, `fielding`, `salaries`, `hall_of_fame`, `allstar`) plus `import_archive`.
- **Tests:** `tests/test_lahman.py` (109 lines), `tests/test_lahman_coverage.py` (229).
- **Spec `lahman-database`:** 6 requirements, 7 scenarios (dual-mode ingestion, typed Parquet, enums, strict schemas for 27 tables, permitted sources only, safe archive import).
- **Docs:** `docs/sources/lahman.md` (935 lines, mostly the generated dictionary); descriptions cover all but 11 of 372 data columns (399 with `_extras`).
- **Currency today:** pinned git ref; the raw tier uses a never-expires TTL and compares `source_ref`; the processed tier is served without any check; ETags are stored, git blob fingerprints are not (tasks 5.1 and 5.2).
- **Owner decisions expected during the review:** stay pinned or float with a time-to-live (5.2); one generic accessor or 27 named functions (5.5); whether to change registry keys that contain nullable columns (1.3, 3.2). Each is asked once, in one short list.
- **Plan review:** an independent Opus 5.5 pass reviewed this plan before any card ran; the standard task table (`scripts/new_source_review.py`) was changed because of it (look-only review tasks 1.x, standard fixes 5.1 to 5.5, tests wait for every fix, new checks for licence, documentation files, cache tiers, repeated-call cost, cross-source id match, names on export, pinned citations).

### Planned spec delta (written in task 2.1; add scenarios with `Verified by` tests)
1. Currency and fingerprints: every raw table records its fingerprint; a changed upstream file is detected by `cache check --upstream`; every cache tier (raw and processed) decides with `is_current()` (matches the `caching-and-invalidation` spec; add the Lahman scenarios).
2. Complete documentation capture: the data dictionary, licence and README are kept in `raw/lahman/` with their hashes, and the licence is stated in `docs/DATA_LICENSES.md`.
3. Complete Python access: every registered table is readable with one documented call.
4. Import path: non-data files of a supplied release are kept; a mixed release is detected; unknown files are not silently registered.
5. Data quality: the orphan checks are order-independent, cover every id column, and their findings are visible to users.
6. Export: all 27 tables verify for every export target; column names survive PostgreSQL; tables whose key has NULLs are refused for merge with the stated message.

## S1 inventory
Done 2026-10-29 (task 1.1, card L-01). Pin `0377e0b8d3` = latest upstream commit.

| Upstream item | Bytes | Dataset | Status |
|---|---|---|---|
| 27 files `data/<Table>.csv` | 42,147,792 | the 27 registered tables | covered |
| `data/readme2025.txt` | 47,976 | none | **gap:** the official data dictionary (every table and column, usage notes, revision history) and the copyright/licence notice; the source for the 11 undescribed columns; not kept (task 5.3) |
| `LICENSE` | 22,240 | none | **gap:** the CC BY-SA 3.0 legal code; not kept (task 5.3) |
| `README.md` | 4,369 | none | **gap:** the mirror's own note (unofficial, unedited re-post of SABR's release of 10 Dec 2025, contacts); not kept (task 5.3) |
| `.gitignore` | 10 | none | not data (repository plumbing); recorded here, deliberately not kept |

- **Licence (read from `LICENSE` and `readme2025.txt`):** Creative Commons Attribution-ShareAlike 3.0 Unported (CC BY-SA 3.0). Copyright 1996-2025 SABR, donated by Sean Lahman; licensing questions to Scott Bush (sbush@sabr.org). Consequence to document (not legal advice): the ShareAlike term applies to adaptations, so exported copies (Parquet, CSV, DuckDB, PostgreSQL) that are shared further carry the same licence and the attribution. `docs/DATA_LICENSES.md` names no licence today; it defers to `readme2025.txt`, which is never stored.
- **Data dictionary facts to use:** missing values are NULL, not zero (section 2.1: "NULLs"); section 2.0 documents the tables; the dictionary's table names differ in case from the real files in places (`AllStarFull`, `HallofFame`, `TeamFranchises` against `AllstarFull.csv`, `HallOfFame.csv`, `TeamsFranchises.csv`), which the description builder must map.
- **Second way in:** SABR distributes the release as `lahman_1871-2025_csv.zip` through a Box.com folder (per the mirror README). No real SABR zip was available in this review, so the import path was read in code only, **not run on a real zip** (OWNER: optionally supply one).
- `uv run baseballpy catalog status --gaps` on an empty home: all 27 Lahman datasets MISSING (as expected before an ingest).

## S2 conformance
Done 2026-10-29 (task 1.2, card L-02).
- `ingest lahman -d <table> --dry-run` is accepted for all 27 registered tables; `lahman:Batting,People` works; an unknown name is rejected with the list of the 27 known names; names are **case-sensitive** (`batting` is rejected).
- The registry, the `LahmanTable` enum and the generated `tables.py` (columns and keys) list the same 27 names. The adapter takes its names from the enum, which is a hand-written parallel list; **no test pins the three lists together** (task 5.7). Other name literals are legitimate: `quality.py` (`Batting`, `People`, `Teams` for specific checks) and `api.py` (`People` for the orphan check).

## S3 schema and types
Done 2026-10-29 (task 1.3, card L-03). Clean ingest of all 27 tables into an empty home: 21.6 s, 41 MB raw to 8.4 MB Parquet, nothing quarantined, `_extras` empty everywhere.
- **Types and values:** no mistyped columns (no string column holds only numbers), no empty strings, no negative integers; 372 data columns. Two columns exist but are always empty: `FieldingOFsplit.WP` and `FieldingOFsplit.ZR` (upstream, document).
- **Keys:** all 27 registry keys are unique (0 duplicate rows). Key columns with NULLs, so `export --mode merge` will be refused for exactly three tables (24 of 27 can merge): `AllstarFull` (`gameNum` 689, `gameID` 738), `AwardsPlayers` (`notes` 2,454), `CollegePlaying` (`yearID` 337). Changing a key is a `scripts/gen_schemas.py` change and an OWNER decision.
- **Orphans inside Lahman:** `playerID` not in `People`: none in any table. (yearID, teamID) not in `Teams`: none, except 5 of 6,425 `AllstarFull` rows. `Teams.franchID`, `HomeGames.parkkey`, `CollegePlaying.schoolID`: none.
- **Against the Chadwick register** (same scratch lake): `People.bbrefID` matches `key_bbref` for 22,981 of 22,995 (99.94%); `People.retroID` matches `key_retro` for 23,337 of 23,373 (99.85%); 22,969 of Chadwick's 24,014 `key_bbref` and 23,316 of its 25,799 `key_retro` values occur in Lahman. 4 people have a `bbrefID` and a `retroID` that point at two different Chadwick persons (`smither02`, `smithge05`, `hughesa01`, `williwo03`: same-name players linked differently by the two projects); 14 `bbrefID` and 36 `retroID` values have no Chadwick row. Lahman `People` has no MLBAM id; MLBAM needs the Chadwick crosswalk. These are provider data differences to document, not our bugs.

## S4 code review against the designated tools
Done 2026-10-29 (task 1.4, card L-04). No code was changed.

| Module | Finding | Verdict |
|---|---|---|
| `adapter.py` (61) | one job per table, names from the enum; the job result never sets `cache_hit` (all 54 `ingest_job` events of two runs say false although 211 of 238 inner `lahman_get_table` events were hits) | task 5.9 |
| `extractor.py` (182) | URLs built from the enum, not the git tree (documentation files never fetched); own `_is_cached` (compares `source_ref`, TTL never expires); stores an ETag fingerprint only; raw `records_count` counts lines including the header (128,599 for 128,598 rows) and the file entry records 0, plus a second dataset-level chunk in the same manifest; `extract_table_async`, `extract_all` and `extract_all_async` have no callers anywhere | tasks 5.1, 5.2, 5.3, 5.8 |
| `api.py` (244) | **cache tier 1 (raw):** `_is_cached`; **tier 2 (processed):** `get_table` returns the Parquet whenever it exists, before the extractor or upstream is asked; local imports are authoritative; 13 hand-written one-line accessors besides the generic `get_table`; `_quality` and `_people_ids` (orphan check runs only if `People` is already stored, rereads it per table); `import_archive` keeps only `*.csv` and turns unknown CSVs into unregistered all-string tables | tasks 5.2, 5.4, 5.5, 5.6 |
| `quality.py` (74) | pure vectorised pyarrow functions, good; checks only `playerID`; findings only logged and stored in the manifest | task 5.6 |
| `normalizer.py` (41), generated `tables.py` | strict schemas by header name, quarantine, drift to `_extras`; fine | keep |
| `schema.py` (58) | the `LahmanTable` enum, a hand-written list of the 27 names; no parity test | task 5.7 |
| `__init__.py` (93) | `lazy_singleton` source (good); 8 hand-written top-level functions | task 5.5 |

- **Timings (real lake, this PC):** `LahmanSource()` construction 18.8 ms; each top-level call re-reads the Parquet: `people()` 8.8 ms, `teams()` 6.3 ms, `batting()` 15.1 ms, `fielding()` 18.2 ms, so 1,000 calls cost 6 to 18 s (Chadwick's per-process cache makes this free; task 5.5). Ingest of all 27 tables 21.6 s.
- **Shared-tool defects found:** `baseballpy cache check --upstream` prints "Upstream was not checked (add --upstream)" even when `--upstream` was given and nothing could be compared (every Lahman file reports `not_checked` because only an ETag is stored); the message should say that no file has a git fingerprint (new task 2.9 of `data-workflow-standard`).
- **Hard rules re-checked:** no `requests`/`urllib.request`/pandas; no swallowed exceptions (architecture tests pass); `httpx` only through `HttpClient`.

## S5 tests and spec gaps
(not started)

## S6 live verification
(not started)

## S7 access, export, descriptions, docs, close
(not started)

## Owner decisions expected (asked once, in one short list; cards continue meanwhile)
1. **Stay pinned or float (task 5.2).** Pinned: the cached copy is current exactly when it was fetched at the locked commit (reproducible; moves only when someone updates the lock). Float with a time-to-live: refreshes itself, but results can change under you. Recommendation: stay pinned (Lahman releases once a year).
2. **One generic accessor or 27 named functions (task 5.5).** Recommendation: one `lahman.table(name)` checked against the registry, keeping the 8 existing named functions.
3. **Keys with NULLs (three tables).** Recommendation: leave the keys as they are and document that merge is refused for `AllstarFull`, `AwardsPlayers`, `CollegePlaying`; changing keys alters what "unique" means and must go through the schema generator.
4. **Case-insensitive table names (task 5.7).** Recommendation: yes, report the canonical name back.
5. **Where users see data-quality findings (task 5.6).** Recommendation: a column in `baseballpy catalog status`.
6. **A real SABR zip (optional, task 5.4).** Supplying `lahman_1871-2025_csv.zip` lets the import path be tested on the real thing; without it the import path is tested on the mirror's folder layout only.
