# Design: v1-coverage-and-smart-concurrency

## 1. Concurrency Architecture Across Sources

### 1.1 The Bottleneck & The Mechanism
`baseballpy.core.http.HttpClient` is built around a single private event loop running in a dedicated thread (`baseballpy-http`). It maintains:
- Per-host `AsyncLimiter` token buckets:
  - `statsapi.mlb.com`: 8.0 req/s
  - `baseballsavant.mlb.com`: 2.5 req/s
  - `raw.githubusercontent.com`: 15.0 req/s
- A global semaphore (`rate_limit_config.max_concurrency`, default 4-8).
- HTTP/2 connection pooling with persistent keep-alive.

Because `HttpClient.get()` (async) and `HttpClient.get_sync()` (sync) both route through `_get_on_loop()`, multiple concurrent workers can safely submit requests without risking rate-limit violations or race conditions.

### 1.2 MLB API Hydrate Fallback Parallelization
In `MlbEndpointExtractor._pool_pages_by_hydrate`:
- Currently, when `v1/stats` returns 406 for league-wide split stats, player IDs are partitioned into batches of `POOL_BATCH = 150`.
- Each batch is fetched sequentially with `self.http.get_sync(...)`. Across 20 sport levels and ~1,500 players, ~150 requests are made sequentially. At ~350ms round-trip per request, sequential execution takes ~54 seconds per endpoint. Across 10 split-stat endpoints, this wastes over 50 minutes.
- **Design:** Dispatch batches concurrently using a `ThreadPoolExecutor(max_workers=self.rate_limit_config.max_concurrency)`.
  - On HTTP 414 (batch URI too long), a sub-batch is retried with halved size.
  - The results are gathered and indexed monotonically so that raw file naming (`{request.ident}.hydrate.p{idx}.json`) remains strictly deterministic.
  - With 8 workers paced at 8 req/s by `HttpClient`, all ~150 batches complete in ~19 seconds instead of 54 seconds.

### 1.3 MLB API Independent Endpoint Ingestion
In `MlbApiSource.ingest_season(season)`:
- Season-scoped endpoints (`teams_season`, `schedule_hydrated`, standings, leaders) are largely independent once reference lists are cached.
- Independent endpoints can be executed concurrently using bounded workers up to `max_concurrency`.

### 1.4 Statcast & Retrosheet Concurrency
- **Statcast:** `_ingest_season_async` already gathers weekly chunk windows using `asyncio.Semaphore(max_concurrency)`. The rate limiter strictly paces requests at 2.5 req/s to prevent Savant 429s. In multi-season queries (`ingest statcast --seasons 2020-2024 -c 2`), the runner's thread pool coordinates multiple season jobs while sharing the same Savant rate limiter.
- **Retrosheet:** Retrosheet downloads event archives and gamelogs from GitHub CDN. The 15 req/s rate limit permits up to 8 parallel workers for fast multi-season unpacking and ingestion.

---

## 2. Expected vs. Held Coverage Auditing (`baseballpy catalog coverage`)

### 2.1 Domain Coverage Principles
A user inspecting their data lake needs to answer:
1. *Do I have all 2,430 regular-season games for 2024?*
2. *Which specific games or dates are missing?*
3. *What exact CLI command will fetch only what is missing?*

### 2.2 Coverage Engine Specification
The `CoverageEngine` operates on a target season (and optional source):
- **MLB API Coverage:**
  - Reads `schedule_hydrated` for the season from the local lake (or prompts to ingest it if missing).
  - Filters for completed regular-season (`R`) and postseason (`F`, `D`, `L`, `W`) games.
  - Inspects held game keys in `game_boxscores`, `game_linescores`, and `game_feed_plays`.
  - Calculates `Held % = (Held Games / Expected Games) * 100`.
  - Collects missing `game_pk` list.
  - Generates exact fix command: e.g. `baseballpy ingest mlb_api --seasons {season} -d games`.
- **Retrosheet Coverage:**
  - Reads `gamelogs` for the season to determine scheduled and completed contests.
  - Checks presence in `box_games` and `events`.
  - Generates exact fix command: e.g. `baseballpy ingest retrosheet --seasons {season} -d events,boxscores`.
- **Statcast Coverage:**
  - Determines expected weekly date windows for the season window.
  - Inspects held partition files in `statcast_pitches`.
  - Generates fix command: e.g. `baseballpy ingest statcast --seasons {season}`.

### 2.3 CLI Interface
```bash
baseballpy catalog coverage [--season YYYY] [--source SOURCE] [--json]
```
Outputs a clean Rich table:
```
┏━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Source     ┃ Season ┃ Expected ┃ Held  ┃ Held % ┃ Remediation Command                            ┃
┡━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ mlb_api    │ 2024   │ 2,430    │ 2,430 │ 100.0% │ (up to date)                                   │
│ retrosheet │ 2024   │ 2,430    │ 2,430 │ 100.0% │ (up to date)                                   │
│ statcast   │ 2024   │ 31       │ 31    │ 100.0% │ (up to date)                                   │
└────────────┴────────┴──────────┴───────┴────────┴────────────────────────────────────────────────┘
```
If gaps exist:
Lists missing game count and outputs the exact command to run.
