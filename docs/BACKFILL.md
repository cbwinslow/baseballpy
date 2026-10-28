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
| MLB API | 2024 (modern) | **incomplete**: 525,784 rows before the run was stopped | 1,273 before the first failure | 843 MB | not measured per season |

Notes on the numbers:

- Resuming is cheap: the whole 2015-2024 window ran again in 46 s with nothing to fetch.
- The 1990 MLB API run overlapped the all-time pools run on the same host, so its time is an upper
  bound.
- The 2024 MLB API season **did not finish**. The first attempt failed after 1,273 s on HTTP 500 for
  `teams/stats` (sport 14), and the retry got HTTP 403 for every `statsapi.mlb.com` request that
  carries our User-Agent (see "Blocker"). So a modern MLB season has no complete time yet; treat
  the 2024 row as a lower bound, and do not extrapolate the MLB API row of the plan below with
  confidence.
- Retrosheet 1990 sizes were not measured separately (the 1990 and 2024 runs shared a lake).

## Blocker found while measuring (needs the owner)

On 2026-10-28, after about three hours of continuous MLB API requests, `statsapi.mlb.com` began
answering 500 and then 403 to our default User-Agent (`baseballpy (+https://github.com/cbwinslow/baseballpy)`).
From this PC and from the homelab the same URLs answer 200 for `curl/8`, `baseballpy/0.1` and
`python-httpx/0.27`; `baseballsavant.mlb.com` answers 200 to our User-Agent. It may be a temporary
block on that client (volume) or a standing rule. I did not change the User-Agent: that would
sidestep a block MLB may have set on purpose. Decision recorded as B-29 in `docs/agents/BACKLOG.md`.

## The plan

Order (cheapest and most valuable first; each stage resumes where it stopped, so interrupting is
safe):

1. **Lahman and Chadwick** (all years): about 1 minute, about 140 MB.
2. **Retrosheet 1871-today** (game logs, events, box accounts): about 155 seasons. Modern seasons
   take about 5.5 minutes each (10 seasons took 53 minutes), early seasons are much smaller, so
   the estimate is **at most 14 hours, realistically 5-8 hours**, and **under 6 GB**
   (about 12 MB processed + 26 MB raw per modern season).
3. **Statcast 2008-today** (pitch level exists from 2008; leaderboards per season): about 18
   seasons at about 6 minutes each for pitches, so **about 2 hours**, and about **8.5 GB**
   (the measured 2015-2024 window was 7.1 GB, raw bytes are 85 percent of it).
4. **MLB API** (per season, then the opt-in all-time pools): not estimable yet (see above). A
   rough bound from the two partial measurements is 18 minutes per old season and well over 20
   minutes per modern one, so **the full history is days, not hours**, and
   **15-25 GB** (2024 alone wrote 843 MB processed). Run it last, per decade, and only after the
   blocker is resolved.

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
3. **MLB API access**: what to do about the 403 (B-29) before stage 4 is attempted.
4. **Schedule**: one long run, or a weekly top-up of the current season (the CI audit workflow
   exists; a scheduled ingest does not).
