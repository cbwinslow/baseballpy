# Design: Unified Pipeline and CLI

## 1. Types
```python
@dataclass(frozen=True)
class Job:
    dataset: DatasetSpec
    params: Mapping[str, Any]        # season, team_id, game_pk, start/end, variant...
    @property
    def chunk_id(self) -> str        # stable, filesystem-safe, deterministic

class JobStatus(StrEnum): COMPLETED, SKIPPED_FRESH, SKIPPED_ABSENT, FAILED, CANCELLED

@dataclass
class JobResult: job, status, rows, bytes, seconds, cache_hit, error, quarantined

class Pipeline:
    def __init__(self, *, config: PipelineConfig | None = None, audit: AuditLogger | None = None, quarantine: Quarantine | None = None)
    async def run(self, job, *, extractor, normalizer, sink, refresh=False) -> JobResult
    async def run_many(self, jobs, *, resolver, sink, concurrency, refresh) -> RunReport
    def plan(self, jobs, *, refresh) -> list[PlannedJob]        # status: WOULD_FETCH | FRESH | ABSENT, with reasons
    def run_sync(...)                                           # drives the shared loop
```
`resolver(job) -> (extractor, normalizer)` comes from the dataset registry (`spec.make_extractor(config)`, `spec.make_normalizer()`), so the pipeline never imports a concrete source (AGENTS §2.1: no splash damage).

## 2. Run algorithm (per job)
1. Check freshness policy using the dataset manifest (`SKIPPED_FRESH`).
2. `extractor.extract_async(**params)` -> raw payload; raw bytes stored via `RawStore` (extractor knows nothing about DuckDB; AGENTS §2.1).
3. `normalizer.normalize(payload)` -> `pa.Table` (bad rows quarantined inside normalizers).
4. `ProcessedStore.put(...)` (atomic Parquet) then optional `sink.write(table, destination, mode="upsert", key_columns=spec.keys)`.
5. Manifest `set_completed(chunk_id, records_count, etag, source_ref, fetched_at)`; on exception `set_failed` + audit FAILURE; on cancellation `CANCELLED`, `.part` files removed.
6. All steps wrapped in one `audit.async_track(operation="pipeline_run", source=spec.source, endpoint=..., destination=...)`.
Concurrency: `asyncio.Semaphore(concurrency)` over jobs (default `RateLimitConfig.max_concurrency`); network limits still enforced by `HttpClient`; CPU parsing offloaded with `asyncio.to_thread` or the process pool for Retrosheet.

## 3. Job generation (selection -> jobs)
Each source registers `JobPlanner.jobs(selection)`:
- `selection.seasons`: parsed from `2023`, `2015-2024`, `2015,2018`, `all` (= all seasons discovered upstream for that dataset; discovery cached).
- Statcast: seasons -> 5-day windows (from the schedule) × `game_types`; leaderboards: seasons × variants.
- MLB: per `fan_out` strategy in the endpoint spec; `per_game` jobs are generated from stored schedules (requires schedule ingested; `ingest` orders dependent datasets automatically via `spec.depends_on`).
- Retrosheet: seasons × datasets from tree discovery; Lahman/Chadwick: one job per table/file.
`ingest all` topologically sorts datasets by `depends_on` (e.g. `mlb.game_feed_*` depends on `mlb.schedule`; `statcast.pitches` depends on `mlb.schedule` only for window bounds and degrades to calendar windows if absent).

## 4. CLI structure
Single module `cli/` package: `cli/__init__.py` (group), `cli/ingest.py`, `cli/catalog.py`, `cli/db.py`, `cli/stream.py`, `cli/docs.py`, `cli/audit.py` (existing code moved), `cli/maintenance.py` (`migrate-layout`, `refs`, `quarantine`, `doctor`). Entry point `baseballpy.cli:main` unchanged. Shared option decorators (`--seasons`, `--sink`, `--destination`, `--refresh`, `--dry-run`, `--concurrency`, `--quiet`, `--json`).
Output: rich tables for humans; `--json` prints one JSON object per job result (JSONL) for scripting. Exit codes: 0 all OK/skipped, 1 any FAILED, 130 cancelled.
`catalog status` columns: dataset, upstream seasons available, seasons ingested, rows, last fetched, freshness (FRESH/STALE/MISSING), notes (`unsupported`, `absent upstream`). This is the user-facing "are we missing anything" check.
`quarantine replay <file>`: loads dead letters, re-normalizes with the current spec, writes recovered rows via the pipeline, and marks the file `.replayed`.
`doctor`: prints resolved paths, env overrides in effect, per-host reachability (HEAD with timeout), disk free, versions, orphan `.part`/lock files (offers `--clean`).

## 5. Protocol conformance contract test
`tests/test_protocol_contract.py` iterates `DATASETS`, builds each extractor/normalizer with a temp config, and asserts: `isinstance` against runtime-checkable protocols AND `inspect.signature` compatibility (parameter names/kinds for `extract`, `extract_async`, `normalize`, `normalize_stream`, `schema`). Sinks asserted for `write`/`write_stream`.

## 6. Config
`get_config()` is `lru_cache`d; `reset_config()` clears it; `PipelineConfig` has `lake`, `audit`, `rate_limit`, `streaming`, `quarantine`, `pipeline` (`default_concurrency`, `default_sink`, `default_destination`). `.env` support only via `BASEBALLPY_ENV_FILE`.

## 7. Test strategy
- Unit: Job id stability, selection parser, topological ordering, plan output.
- Integration with respx + tmp lake: `Pipeline.run_many` over 3 fake datasets; kill mid-run via task cancel -> `CANCELLED` + resumable; re-run skips completed; `--dry-run` makes zero HTTP calls; failures produce non-zero exit.
- CLI tests with `click.testing.CliRunner` for every command (help text, JSON output, exit codes).
- Manual end-to-end: `baseballpy ingest all --seasons 2023 --sources lahman,chadwick,retrosheet,mlb --dry-run` then real run into a scratch home; `catalog status` shows no MISSING; `db query "select count(*) from statcast_pitches"` works.
