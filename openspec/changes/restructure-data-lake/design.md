# Design: Restructure the Data Lake

## 1. LakeConfig
```python
class LakeConfig(BaseSettings):            # env_prefix BASEBALLPY_
    home: Path = ~/.baseballpy             # BASEBALLPY_HOME
    raw_root_override / processed_root_override / quarantine_root_override / http_cache_root_override / database_path_override
    def raw_dir(source, dataset, season=None) -> Path        # creates lazily on write, NOT on property access
    def processed_dir(source, dataset, season=None) -> Path
    def dataset_manifest(source, dataset, tier="processed") -> ManifestTracker
```
- Directory creation moves out of property getters (previous design created dirs on read). Helpers take `create: bool = False`.
- `get_default_base_dir()` precedence: `BASEBALLPY_HOME`, else legacy `BASEBALLPY_CACHE_DIR` parent (deprecated, warns), else `~/.baseballpy`.
- `PipelineConfig` composes `lake`, `audit`, `rate_limit`, `streaming`, `quarantine` (see harden change).

## 2. Dataset registry (shared with coverage change)
`core/datasets.py` defines:
```python
@dataclass(frozen=True)
class DatasetSpec:
    source: str  # "statcast" | "mlb_api" | "lahman" | "chadwick" | "retrosheet"
    name: str  # "pitches", "schedule", "Batting", ...
    view: str  # DuckDB view name, e.g. "statcast_pitches"
    schema: pa.Schema
    partition: Literal["season", "none"]
    keys: tuple[str, ...]  # natural/primary key columns used for upserts and dup tests
    description: str
    endpoint_doc: str  # relative link to docs/sources/<source>.md anchor


DATASETS: dict[str, DatasetSpec]  # keyed "<source>.<name>"
```
All of: path derivation, view creation, doc generation, the CLI `ingest` command and tests iterate `DATASETS`; nothing hardcodes a dataset name elsewhere.

## 3. Raw and processed writes
`RawStore.put(source, dataset, name, bytes, season=None, source_ref=None)` -> atomic write to `raw/...`, records sha256 and size in the dataset manifest. `ProcessedStore.put(spec, table, season=None, chunk_id)` -> `atomic_write_parquet` to `processed/<source>/<dataset>/[season=YYYY/]part-<chunk_id>.parquet`. Parquet footer is validated (`pq.ParquetFile(part).metadata`) before the atomic rename (AGENTS §8.1). Re-parsing from `raw/` without network is a first-class path: `reprocess(spec, season)`.

## 4. BaseballDatabase
```python
for spec in DATASETS.values():
    files = glob(processed_dir(spec) / ("**/*.parquet"))
    if files: CREATE OR REPLACE VIEW {spec.view} AS SELECT * FROM read_parquet('{glob}', hive_partitioning=true, union_by_name=true)
```
- Paths are passed as single-quoted literals after escaping `'`; view names are validated identifiers (`quote_ident`).
- `season` hive column is cast consistently: for partitioned datasets whose schema already has `season`, `hive_types={'season': 'SMALLINT'}` is set and the duplicate column is avoided (`hive_partitioning` + physical column collision is tested explicitly).
- `read_only=True`: if all registered views already exist, return count; otherwise raise `DatabaseReadOnlyError` naming `baseballpy db sync`.
- Always-on convenience views: `v_player_crosswalk` (Chadwick register), `v_season_catalog` (what seasons exist per dataset from manifests).
- Registration is audited once with `records_count = views_registered`.

## 5. Layout migration (`core/migrate.py`)
Detection: `VERSION` file missing and any of `cache/statcast`, `cache/retrosheet`, `cache/lahman`, `cache/chadwick`, `cache/mlb_api` exists.
Mapping table (v1 -> v2):
| v1 | v2 |
|----|----|
| `cache/statcast/season=Y/*.parquet` | `processed/statcast/pitches/season=Y/part-*.parquet` |
| `cache/statcast/<flat>.parquet` | same, season from filename |
| `cache/statcast/leaderboards/<name>_<year>*.parquet` | `processed/statcast/leaderboard_<name>/season=<year>/part-*.parquet` |
| `cache/retrosheet/raw/<year>/*` | `raw/retrosheet/event_files/season=<year>/*` (rosters to `raw/retrosheet/rosters/season=<year>/`) |
| `cache/retrosheet/raw/gamelogs/*`, `reference/*` | `raw/retrosheet/gamelogs/...`, `raw/retrosheet/reference_<name>/` |
| `cache/retrosheet/processed/events/season=Y/events.parquet` | `processed/retrosheet/events/season=Y/part-events.parquet` |
| `.../events_all.parquet` | `processed/retrosheet/events_postseason/season=Y/part-events_all.parquet` |
| other `processed/<x>/season=Y/*` | `processed/retrosheet/<x>/season=Y/...` |
| `cache/lahman/raw/*.csv` / `processed/*.parquet` | `raw/lahman/<Table>/<Table>.csv` / `processed/lahman/<Table>/data.parquet` |
| `cache/chadwick/shards`, `names.csv`, `links.csv`, `processed/register.parquet` | `raw/chadwick/register/...`, `processed/chadwick/register/data.parquet` |
| `cache/mlb_api/<category>/<ident>.parquet` | concatenated per category/season into `processed/mlb_api/<dataset>/season=Y/part-*.parquet` (schedule/standings/transactions/draft by year in ident; teams/venues flat) |
Behavior: copy (not move) unless `--delete-old`; verify row counts after copy; write `VERSION=2` last; skip files that already exist with equal size+sha256; print a summary table (moved/skipped/unknown). `--dry-run` prints the plan only.

## 6. Pinned refs (L-8)
`core/sources_lock.py`: `LOCK = {"retrosheet": {"repo": "chadwickbureau/retrosheet", "ref": "<sha>"}, "chadwick_register": {...}, "lahman": {...}}`. `refs update` queries `GET /repos/{repo}/commits?per_page=1` (through `HttpClient`, authenticated if `GITHUB_TOKEN` is set to avoid the 60/h limit), rewrites the lock file, and prints the diff. URLs are built as `https://raw.githubusercontent.com/{repo}/{ref}/{path}`. Manifest `source_ref` makes a ref change invalidate affected chunks.

## 7. Test strategy
- Unit: `LakeConfig` env overrides and no-dir-creation-on-read; registry completeness (every dataset has schema, keys, view, doc anchor).
- Integration (tmp_path): build a synthetic v1 tree, run migration, assert v2 tree + row-count equality + idempotency; build views and assert no duplicate rows when both `events` and `events_postseason` exist; assert leaderboard data never appears in `statcast_pitches`; read-only behavior.
- Manual: run migration with `--dry-run` against the author's real `~/.baseballpy`, review, run for real, run `baseballpy db sync` and count rows per view before/after.
