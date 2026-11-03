# Design: auto-concurrency-and-intra-source-parallelism

## Architectural Overview

```text
User CLI (`baseballpy ingest all -s 2024`)
      │
      ▼ (concurrency=None / auto)
resolve_concurrency(concurrency, job_count)
      │
      ├─ CPU Count detection: min(32, max(2, os.cpu_count() or 4))
      ├─ Bounded by planned job count
      ▼
run_jobs(planned_jobs, adapters, concurrency=auto_concurrency)
      │
      ├─ ThreadPoolExecutor(max_workers=auto_concurrency)
      ▼
Worker Threads (Parallel Ingestion)
      │
      ├── Chadwick / Lahman (Local I/O & Network)
      ├── Retrosheet (Zip Download & Parser Pool)
      ├── Statcast (AsyncLimiter: 2.5 req/s)
      └── MLB API (AsyncLimiter: 8.0 req/s, Game Feed Pool)
```

## Concurrency Resolution Formula
```python
def resolve_concurrency(
    concurrency: int | str | None = None,
    job_count: int | None = None,
    max_cap: int = 32,
) -> int:
    """Calculate the optimal worker thread count for ingestion jobs."""
    if concurrency is None or str(concurrency).strip().lower() == "auto":
        cpus = os.cpu_count() or 4
        # Standard I/O worker heuristic: scale with cores, minimum 2, capped at max_cap
        target = min(max_cap, max(2, cpus))
        if job_count is not None and job_count > 0:
            return min(target, job_count)
        return target
    
    try:
        val = int(concurrency)
    except (ValueError, TypeError):
        raise ValueError(f"concurrency must be an integer >= 1 or 'auto'; got {concurrency!r}")
    
    if val < 1:
        raise ValueError(f"concurrency must be at least 1; got {val}")
    return val
```

## Intra-Source Parallelism Details
1. **MLB Stats API:**
   - In `MlbApiSource.ingest_season(..., include_games=True)`:
     When fetching game endpoints across hundreds or thousands of `game_pk`s, games are chunked and executed with `max_workers = min(resolved_concurrency, 16)`.
   - All requests route through `HttpClient` where the host token bucket (8 req/s) prevents 429 errors.
2. **Statcast Leaderboards & Chunks:**
   - Multiple leaderboard slugs run concurrently bounded by `resolved_concurrency`.
   - Date chunks for pitch data utilize worker pools bounded by `resolved_concurrency` and Savant's 2.5 req/s rate limiter.
3. **Audit Trail Synchronization:**
   - `AuditLogger` uses a `threading.Lock()` and file append mode with explicit flushes, ensuring that 2 to 32 parallel threads record audit events with zero interleaving or record loss.

## Non-Breaking Invariants
- Explicit `--concurrency N` (e.g. `--concurrency 1` or `-c 4`) behaves identically to previous releases.
- Zero external dependencies introduced (`os.cpu_count()` and standard library `concurrent.futures`).

## As Built & Verification Evidence
- `resolve_concurrency` implemented in `src/baseballpy/core/concurrency.py`.
- `run_jobs` in `src/baseballpy/ingest/runner.py` accepts `concurrency: int | str | None = None` and auto-resolves with bounds.
- `baseballpy ingest` CLI in `src/baseballpy/cli_ingest.py` defaults to `auto` concurrency and displays resolved worker count in UI.
- All 1,213 test cases passed in 296s (`tests/test_auto_concurrency.py`, `tests/test_ingest_runner.py`, `tests/test_cli_ingest.py`).
- Strict typing (114 modules clean with `mypy --strict src`), linting (`ruff check .`), formatting (`ruff format --check .`), and docs sync (`baseballpy docs generate --check`) green.

