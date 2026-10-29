# Tasks: dlt-pipeline-core

- [x] 1. Spike (bounded: three endpoints, about 20 requests, one at a time)
  - [x] 1.1 Brief and a registry-driven resource factory that yields `teams`, `schedule` (one day) and `people_stats_season_hitting` (three people) as dlt resources; agy drafts, Claude reviews
  - [x] 1.2 Load into DuckDB and filesystem Parquet with `schema_contract` evolve; compare columns, types, row counts and code size with the current path
  - [x] 1.3 Record in design.md what dlt replaced and what it could not (raw bytes, quarantine, rate limit, strict types)
- [x] 2. Decision
  - [x] 2.1 ADR 42, adopt or reject, citing the spike numbers
- [ ] 3. Adoption (only if ADR 42 adopts)
  - [ ] 3.1 `DltAdapter` behind `IngestAdapter`, resources generated from the dataset registry, `HttpClient` passed as dlt's session so rate limits and the User-Agent stay in one place
  - [ ] 3.2 Retire the flatten, `_extras` and drift paths that schema contracts replace; tests; docs
