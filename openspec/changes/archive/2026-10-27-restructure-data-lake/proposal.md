# Change Proposal: Restructure the Local Data Lake (raw / processed / quarantine / cache)

## Context & Motivation
Today the directory named `cache/` is also the dataset: Parquet that analysts query lives next to
throw-away HTTP responses, `BaseballDatabase` builds views over `cache/`, and the TTL logic added by
`harden-ingestion-core` could delete real data. Layouts differ per source (Statcast has no raw/processed
tiers, MLB API writes one Parquet file per id), and two datasets can share one Hive partition
(`events.parquet` + `events_all.parquet`), duplicating rows in views. Leaderboard Parquet sits under
`statcast/leaderboards/` and is globbed into the `statcast_pitches` view. AGENTS §8.3 mandates a clean
`raw/` vs `processed/` split.

## Findings Fixed (IDs `L-n`)
| ID | Defect |
|----|--------|
| L-1 | `cache/` doubles as the data store; pruning the cache would destroy datasets. |
| L-2 | Inconsistent tiering; Statcast, MLB API and leaderboards have no `raw/`. |
| L-3 | `statcast_pitches` view globs `statcast/**/*.parquet` and ingests leaderboard files. |
| L-4 | `events.parquet` and `events_all.parquet` in one `season=` folder duplicate regular-season rows in `retrosheet_events`. |
| L-5 | No views for MLB API, Retrosheet rosters/daily splits/substitutions/reference/postseason logs, leaderboards, Chadwick names/links. |
| L-6 | `CREATE VIEW` fails when `read_only=True`. |
| L-7 | `database.py` repeats the same ~20-line block seven times. |
| L-8 | Remote refs are floating (`master`/`main`); results are not reproducible. |
| L-9 | Stray `test.duckdb`/`test2.duckdb` in repo root; no migration path for existing user data. |

## Target Layout (authoritative)
```text
$BASEBALLPY_HOME (default ~/.baseballpy)
├── raw/<source>/<dataset>/[season=YYYY/]<original files>       immutable upstream bytes (+ manifest.json per dataset dir)
├── processed/<source>/<dataset>/[season=YYYY/]part-<chunk>.parquet   typed Parquet, Hive-partitioned, one dataset per directory
├── quarantine/<source>/<YYYY-MM-DD>/<dataset>-<id>.jsonl        dead letters
├── cache/http/                                                   ETag/TTL bookkeeping only; safe to delete
├── databases/baseball.duckdb                                     views only (no data copies) over processed/
├── logs/audit.jsonl
└── VERSION                                                       layout version integer (this change = 2)
```
Rules:
1. Views read only `processed/`. `raw/` is never read by views. `cache/` never holds datasets.
2. One dataset per directory. Regular and postseason Retrosheet events are distinct datasets (`events`, `events_postseason`), never sibling files in one partition.
3. Partition key `season=YYYY` wherever data has a season; non-seasonal reference data is flat (`processed/<source>/<dataset>/data.parquet`).
4. Partition file names are `part-<chunk_id>.parquet` so reruns overwrite deterministically.
5. Every dataset directory has a `manifest.json` (chunk status, `records_count`, `etag`, `fetched_at`, `source_ref`).

## Proposed Changes
1. `LakeConfig` (pydantic-settings, `BASEBALLPY_` prefix): `home`, `raw_root`, `processed_root`, `quarantine_root`, `http_cache_root`, `database_path`, with helpers `raw_dir(source, dataset, season=None)` and `processed_dir(source, dataset, season=None)`. `CacheConfig` remains as a deprecated alias (emits `DeprecationWarning`), its per-source properties mapping onto `processed/`.
2. Every source writes raw bytes to `raw/` and typed Parquet to `processed/`, both atomically, using the dataset catalog from `complete-source-coverage`.
3. `BaseballDatabase` becomes table-driven via `DATASET_REGISTRY`; read-only connections skip view creation with a clear error if views are missing; `baseballpy db sync` opens read-write.
4. `baseballpy migrate-layout [--dry-run] [--delete-old]` and `baseballpy.migrate_layout()` move v1 data into v2, write `VERSION`, are idempotent, and report (not move) unknown files. A v1 tree is detected at first use and a one-line migration hint is logged; nothing is auto-moved.
5. Pin remote refs: manifests record `source_ref` (commit SHA); `BASEBALLPY_RETROSHEET_REF`, `BASEBALLPY_CHADWICK_REF`, `BASEBALLPY_LAHMAN_REF` default to SHAs recorded in `core/sources_lock.py`; `baseballpy refs update` resolves latest SHAs via the GitHub API and rewrites the lock.
6. Delete `test.duckdb` and `test2.duckdb` from the repo root.

## Out of Scope
New endpoints/tables (`complete-source-coverage`); CLI beyond `migrate-layout`, `db sync`, `refs update` (`unified-pipeline-and-cli`).

## Impact
Anyone with v1 data must run `migrate-layout` once. Recorded in ADR 23.
