# Backfill: throughput and the plan for the full history

How long and how much disk a historical backfill takes, measured on the homelab (`cbwdellr720`,
one request at a time, `--concurrency 1`) on 2026-10-28, and the plan built from it. `baseballpy
backfill PLAN.toml` runs a plan (see `docs/CLI.md`); this page says what to put in it.

## Measured

Rows and seconds come from the `ingest --json` job reports of the homelab runs; sizes are `du` of
the lake directories (`processed/` is zstd Parquet, `raw/` is the upstream bytes).

| Source | Season(s) | Rows | Seconds | Processed | Raw |
|---|---|---|---|---|---|
| Lahman (27 tables) | all | 706,466 | 13.6 | 9 MB | 41 MB |
| Chadwick register | all | 526,894 | 16.7 | 24 MB | 66 MB |
| Retrosheet | 1990 (old) | 519,051 (+90,646 reference) | 292 (+9) | see below | see below |
| Retrosheet | 2015-2024 (10 seasons) | 5,943,007 | 3,179 | 117 MB | 262 MB |
| Statcast pitches + leaderboards | 2008 (old) | 794,241 + 2,941 | 355 + 27 | 72 MB | 406 MB |
| Statcast pitches + leaderboards (+ minors from 2021) | 2015-2024 | 10,431,131 + 185,090 | 5,941 + 276 | 1,066 MB | 6,040 MB |
| MLB API | 1990 (old) | 384,031 (+5,317 reference) | 1,058 (+6) | 121 MB | not measured per season |
| MLB API | 2024 (modern) | 654,821 | 3,061 in the completing run (+1,273 in the first run that failed on HTTP 500; finished chunks were kept) | 966 MB | not measured per season |

Notes on the numbers:

- Resuming is cheap: the whole 2015-2024 window ran again in 46 s with nothing to fetch.
- The 1990 MLB API run overlapped the all-time pools run on the same host, so its time is an upper
  bound.
- The 2024 MLB API season needed two runs: the first failed after 1,273 s on HTTP 500, then every `statsapi.mlb.com` request got HTTP 403 for our old User-Agent (see "Blocker"). After the User-Agent change (ADR 40) the resumed run finished in 3,061 s, so a modern season takes about 1.2 hours in all.
- Retrosheet 1990 sizes were not measured separately (the 1990 and 2024 runs shared a lake).

## Speed after the 2026-11-03 speed work (this PC, 56 logical CPUs, 96 GB RAM)

The table above is the homelab run of 2026-10-28 (one request at a time). After ADR 57, 59, 60 and
61 the same work runs much faster here; every number is a fresh lake, measured with
`logs/audit.jsonl` and the `ingest` report. Details and the failed ideas (adaptive concurrency,
ADR 58) are in the archived changes `2026-11-03-*`.

| Source | Work | Before | Now | What changed |
|---|---|---|---|---|
| MLB API | season 2024 (12,309 requests, 928,792 rows) | 3,234 s | **1,749 s** | requests of one endpoint run together, per-host limits, 10 requests/s (ADR 57, 59) |
| Retrosheet | one season (2022, 628,348 rows) | 236.5 s | **35.6 s** | parsing on 32 worker processes through one shared pool (ADR 61) |
| Retrosheet | five seasons (2018-2022) together | about 1,185 s | **98 s** | same |
| Statcast | 2024: pitches 826,759 + minors 867,883 + leaderboards 21,442 rows, one command | about 1,038 s (443 + 516 + 79) | **380 s** (295 + 375 + 146 at the same time) | jobs run together, Savant at 8 requests in flight (ADR 57) |
| Lahman + Chadwick | all tables and the register | 13.6 + 16.7 s | **13 s** | nothing needed |

What limits each source now:

- **MLB API:** the host rate (10 requests/s, the top of the `AGENTS.md` range); a few endpoints
  (`stats_leaders`) are slow on the provider's side and get slower with more concurrent requests.
- **Retrosheet:** CPU (parsing) and about 25 s of GitHub downloads per season.
- **Statcast:** Savant's server, about 2,300-3,100 rows/s per stream; more requests in flight
  did not help (8 against 16 gave the same rows per second); each 5-day window takes about 40 s.
- Both MLB API and Savant cache repeated requests: always benchmark on a season or date range
  that has not been requested before.

## Blocker found while measuring (resolved)

On 2026-10-28, after about three hours of continuous MLB API requests, `statsapi.mlb.com` answered 500 and then 403 to our default User-Agent for more than two hours of retests, while `curl/8`, `python-httpx/0.27`, `baseballpy/0.1` and `python-requests/2.32.3` got 200 and Savant was unaffected. The owner chose to send the string pybaseball sends (ADR 40, overridable with `BASEBALLPY_USER_AGENT`); the same URLs then answered 200 and the season finished.

## The plan

Order (cheapest and most valuable first; each stage resumes where it stopped, so interrupting is
safe):

1. **Lahman and Chadwick** (all years): about 1 minute, about 140 MB.
2. **Retrosheet 1871-today** (game logs, events, box accounts): about 155 seasons. Modern seasons
   take about 36 seconds each alone and about 20 seconds each when several run together (five
   seasons took 98 s, ADR 61; it was 5.5 minutes each on the homelab), early seasons are much
   smaller, so the estimate is **at most about 1 hour, realistically 30-40 minutes**, and
   **under 6 GB** (about 12 MB processed + 26 MB raw per modern season).
3. **Statcast 2008-today** (pitch level exists from 2008; leaderboards per season): a modern season
   takes about 6.3 minutes with pitches, minors and leaderboards together (2021 on), about 5
   minutes for the older ones, so **about 1.5 hours** for 18 seasons, and about **8.5 GB**
   (the measured 2015-2024 window was 7.1 GB, raw bytes are 85 percent of it).
4. **MLB API** (per season, then the opt-in all-time pools): a modern season (2024) now takes
   29 minutes (it took 1.2 hours); an old season such as 1990 was 18 minutes and, scaled by the
   same factor (an estimate, not measured), would take about 10 minutes, so **the full history is
   about 55 hours** (about two days of running; estimated from the old 100 hours), and about **0.12 GB per old season and 1 GB per modern one**, so roughly
   **15-25 GB** in all. Run it last, per decade. **Blocked in part (2026-10-29):** league-wide `v1/stats` answers HTTP 406 (backlog B-30), so the `stats_*` datasets of every season, and the all-time pools, are missing until it answers 200 again.

A plan file for stages 1-3 (example, edit the ranges):

```toml
[[stage]]
name = "reference"
sources = ["lahman", "chadwick"]
estimate_gb = 0.2

[[stage]]
name = "retrosheet-modern"
sources = ["retrosheet"]
seasons = "2000-2025"
estimate_gb = 1.0

[[stage]]
name = "statcast"
sources = ["statcast"]
seasons = "2008-2025"
estimate_gb = 8.5
```

Run it with `baseballpy backfill plan.toml --max-gb 15 --dry-run` first (it prints the stages and
refuses to start when the free space would fall under the floor).

## Decisions only the owner can make

1. **Permanent location of the lake** (`BASEBALLPY_HOME`): this PC lacks the space for stage 4, the
   homelab has about 136 GB free.
2. **Ranges**: how far back for each source (Retrosheet from 1871? Statcast from 2008 or 2015?
   minor leagues from 2021?).
3. **MLB API etiquette**: stage 4 is about 100 hours of requests to one host; the block above shows MLB reacts to volume or to the agent string, so run it in decade chunks.
4. **Schedule**: one long run, or a weekly top-up of the current season (the CI audit workflow
   exists; a scheduled ingest does not).
