# Change Proposal: v1-coverage-and-smart-concurrency

## 1. Intent & Context
As `baseballpy` approaches its polished v1 release, two critical production capabilities remain essential for users and modeling teams:
1. **High-Impact Smart Concurrency:** Downloading large baseball datasets sequentially currently bottlenecks pipelines. For example, in MLB Stats API, the hydrate fallback for split stats queries ~1,500 players across 20 sport levels in ~150 batches; fetching these sequentially achieves only ~0.5 req/s (~54 minutes), even though `statsapi.mlb.com` allows 8-10 req/s. Similarly, multi-season Statcast pitch downloads and multi-season Retrosheet archive extractions should leverage bounded concurrency without exceeding upstream token-bucket rate limits.
2. **Expected vs. Held Coverage Auditing (`catalog coverage`):** While `catalog status --gaps` reports missing datasets in the local lake, users require an actionable game-level and entity-level audit per season (e.g., comparing 2,430 scheduled regular-season games against held records in `game_feed_plays`, `game_boxscores`, `game_linescores`, and `statcast_pitches`), displaying held percentages, identifying specific missing IDs, and outputting exact remediation CLI commands.

## 2. Proposed Changes
- **MLB API Smart Concurrency:**
  - Parallelize hydrate fallback batch requests (`_pool_pages_by_hydrate`) using a bounded worker pool (`ThreadPoolExecutor` or `asyncio.gather`) throttled by `HttpClient`'s 8 req/s token bucket.
  - Enable bounded concurrent extraction of independent season-scoped endpoints in `MlbApiSource.ingest_season`.
- **Cross-Source Concurrency Verification:**
  - Verify and optimize concurrency across Statcast (Savant token bucket at 2.5 req/s) and Retrosheet (GitHub CDN at 15 req/s).
  - Ensure the unified CLI `--concurrency` flag smoothly coordinates worker pools while strict per-host rate limits prevent 429s.
- **Expected vs. Held Coverage Command (`baseballpy catalog coverage`):**
  - Implement `baseballpy catalog coverage [--season YYYY] [--source SOURCE] [--json]`.
  - For MLB API: inspect `schedule_hydrated` for final game PKs and compare against held rows in game-level datasets (`game_feed_plays`, `game_boxscores`, `game_linescores`).
  - For Retrosheet: compare `gamelogs` against `box_games` and `events`.
  - For Statcast: compare expected weekly date windows against ingested chunks.
  - Print a clear Rich table showing expected counts, held counts, held percentage, and exact copy-paste CLI commands to backfill missing games or tables.
- **V1 Cleanups & System Specs:**
  - Add spec deltas to `openspec/specs/concurrency-and-rate-limiting/` and `openspec/specs/catalog-audit/`.
  - Update `docs/CLI.md` with coverage commands and concurrency options.

## 3. Impact & Compatibility
- **Zero Splash Damage:** All changes preserve existing schemas, Arrow table structures, and `IngestAdapter` contracts.
- **Dramatic Speedup:** Ingestion of full MLB seasons drops from ~54 minutes to under 5 minutes without any risk of 429s or IP bans.
- **High User Confidence:** Users can instantly audit their data lake for 100% complete season coverage and copy-paste remediation commands for any missing games.
