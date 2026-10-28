# Change Proposal: Unified Pipeline, Full-Surface CLI, and One-Command Ingest

## Context & Motivation
AGENTS §2.2 mandates `Pipeline.run(extractor, normalizer, sink)`; it does not exist. The CLI covers only
`statcast` and `audit`, so most sources cannot be ingested from the command line. There is no way to say
"ingest everything" or to see what has been ingested. Findings (IDs `P-n`):

| ID | Gap |
|----|-----|
| P-1 | No `Pipeline` class; workflows are ad-hoc per source (monolithic `*Source` classes mixing fetch/parse/save). |
| P-2 | CLI lacks MLB API, Lahman, Chadwick, Retrosheet, leaderboards, streaming, db, docs, migration, refs, catalog. |
| P-3 | No `ingest --all`, no progress display, no dry-run, no resume summary. |
| P-4 | `PipelineConfig`/`get_config()` unused; `.env` read implicitly from cwd. |
| P-5 | Extractor/normalizer protocols are not satisfied by Lahman, leaderboards, MLB, streamer (signature mismatch); no contract test. |
| P-6 | Sync entry points run `asyncio.run` per call (statcast) or a thread-per-call; no shared loop. |

## Proposed Changes
1. `baseballpy.pipeline`: `Pipeline(extractor, normalizer, sink, *, quarantine, audit)` with `run(job) -> RunReport`, `run_many(jobs, concurrency)`, `plan(jobs)` (dry-run). `Job` = `(dataset: DatasetSpec, params: Mapping)`; `RunReport` = per-job status (`COMPLETED|SKIPPED_FRESH|SKIPPED_ABSENT|FAILED|CANCELLED`), rows, bytes, duration, cache_hit, error. Pause/resume via dataset manifests; Ctrl-C produces `CANCELLED` and a resumable state.
2. Source adapters: each source provides `jobs_for(selection) -> Iterable[Job]` (seasons, teams, games, leaderboard variants...). The existing `*Source` orchestrator classes become thin facades over `Pipeline` (public function names unchanged).
3. Protocol fixes: every registered extractor satisfies `ExtractorProtocol` (`extract`, `extract_async`), every normalizer `NormalizerProtocol`; a signature-level contract test enforces it (`inspect.signature`).
4. CLI (click + rich), all commands audited:
   - `baseballpy ingest <source> [dataset ...] [--seasons 2023 | 2015-2024 | all] [--start --end] [--teams] [--game-pk] [--refresh] [--sink duckdb|parquet|dlt] [--destination] [--dry-run] [--concurrency N]`
   - `baseballpy ingest all [--seasons ...] [--sources statcast,mlb,...] [--dry-run]`
   - `baseballpy catalog list|show <dataset>|status` (what exists, row counts, seasons present, last fetched, freshness, gaps vs upstream-available seasons)
   - `baseballpy db sync|shell|query "<sql>"|views`
   - `baseballpy stream <game_pk> [--sink] [--jsonl -]`
   - `baseballpy docs generate|check`
   - `baseballpy migrate-layout`, `baseballpy refs update|show`
   - `baseballpy audit summary|tail|stats [--source --since --status]` (existing, extended filters)
   - `baseballpy quarantine list|show|replay` (replay re-runs normalization of quarantined payloads after a schema fix)
   - `baseballpy doctor` (config dump, directories, free disk, DuckDB/Arrow versions, upstream reachability per host, lock files, stale `.part` files)
5. Progress UX: `rich.progress` with per-dataset bars, ETA, rows/s; `--quiet`/`--json` for machine output; non-zero exit codes on any FAILED job.
6. Sync/async: one background event loop owned by `HttpClient` (see harden change); `Pipeline.run_sync()` drives it; no more per-call `asyncio.run`.
7. Config: `PipelineConfig` is the single entry (`get_config()` lazy, resettable via `reset_config()` for tests); `.env` loading only when `BASEBALLPY_ENV_FILE` is set.

## Out of Scope
Server/daemon mode, MCP server, Rust accelerators (remain in ROADMAP).

## Impact
Additive CLI. Existing Python API unchanged. Recorded in ADR 25.
