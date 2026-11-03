# Tasks: request-parallelism-and-host-limits

- [x] 1.1 Per-host in-flight limits in `HttpClient` (`host_concurrency` config), connection pool sized from the limits.
- [x] 1.2 MLB request-level parallelism in `ingest` and `_ingest_raw_only` (bounded pool, fail-fast, 404 counter summed).
- [x] 1.3 `baseballpy ingest` states the worker count and the network limit; QUICKSTART and CLI docs.
- [x] 1.4 Tests that prove it: per-host isolation, peak in flight bounded, runner jobs run in parallel, one MLB endpoint's requests overlap, fail-fast, missing count.
- [x] 1.5 Benchmark before and after on a fixed MLB subset, numbers in design.md.
- [x] 1.6 Measure Savant in-flight (4 vs more) live, record the evidence, change a default only with it.
- [x] 1.7 Specs, `AGENTS.md` section 4, ADR 57, gates, archive.
