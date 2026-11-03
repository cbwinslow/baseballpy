# Proposal: auto-concurrency-and-intra-source-parallelism

## Problem Statement
1. **Manual Concurrency Burden:** Currently, `baseballpy ingest` requires users to manually specify `--concurrency N` (or default to 1, or 4 in certain contexts) to achieve parallel downloads. On high-end multi-core machines (e.g. 56-core workstations) or standard multi-core laptops, users should not have to guess thread counts. Instead, the runner should automatically scale concurrency to the hardware capacity without risking socket or memory exhaustion.
2. **Within-Source Multi-Threading:** While top-level jobs (across different datasets or sources) can run concurrently, intra-source operations (e.g., fetching multiple game live feeds, multiple seasons, or multiple Statcast dates) should scale with auto-detected concurrency while respecting domain-specific rate limits.
3. **Ergonomic CLI:** `--concurrency` should accept `auto` (the default when omitted or set to None/auto) while retaining optional explicit integer overrides for constrained environments.

## Proposed Solution
1. **`resolve_concurrency(concurrency: int | str | None = None, job_count: int | None = None) -> int`:**
   Add a centralized concurrency resolver in `baseballpy.core.concurrency` (or `ingest.runner`):
   - If `concurrency` is `None` or `"auto"`, calculate:
     `auto_threads = min(32, max(2, (os.cpu_count() or 4)))`
     If `job_count` is provided, bound by `min(auto_threads, max(1, job_count))`.
   - If an integer is passed (e.g., `concurrency=8`), validate `>= 1` and use it.
   - If `concurrency <= 0`, raise `ValueError`.
2. **CLI Option Update:**
   Update `@click.option("--concurrency", "-c")` in `cli_ingest.py` to allow optional values (defaulting to auto resolution) and show the resolved concurrency in the console output:
   `[dim]Auto-concurrency enabled: N parallel workers[/dim]`.
3. **Within-Source Worker Scaling:**
   Ensure `MlbApiSource` (game feeds, reference, season endpoints), `StatcastLeaderboards`, and `RetrosheetDownloader` adapt to the configured concurrency rather than hard-coding low constants like 4 or 8.

## Scope
- `src/baseballpy/core/concurrency.py`: Auto-concurrency resolver utility function.
- `src/baseballpy/ingest/runner.py`: Integrate auto-concurrency resolution into `run_jobs`.
- `src/baseballpy/cli_ingest.py`: Update `--concurrency` option to default to auto-resolution and display active worker count.
- `tests/test_auto_concurrency.py`: Unit tests verifying resolution on various CPU counts, validation errors, and execution behavior.
