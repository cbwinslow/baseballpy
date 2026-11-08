# Design: data needs for the game-winner model

Status of the "Have" column: written from the source docs and the dataset registry, **not yet verified against the lake** (task 1.1). "As of" means safe to use before first pitch in a backtest.

## The one rule that matters: as-of safety
A model may only use facts that were known before the game started. Final box scores, final standings, season totals and Savant leaderboards for the same season are NOT as-of safe for games inside that season. Features are built from a rolling cut-off date. Anything without a timestamp is treated as unsafe until proven otherwise.

## Field list

| Need | Used for | Source | Have? | As-of safe? | Notes |
|---|---|---|---|---|---|
| Game schedule, teams, venue, start time, doubleheader flag, final score | the label and the base table | MLB `/v1/schedule`, Retrosheet gamelogs | Yes (233,634 gamelogs 1871-2026) | Schedule yes; score is the label only | Retrosheet gamelogs tie out MLB since 1871 |
| Probable starting pitchers | starter quality, the biggest single input | MLB schedule `hydrate=probablePitcher`, Retrosheet box_starters | Yes (4,147,490 starters in box_starters) | Only with a snapshot time | Needs timestamped snapshots for live games; Retrosheet box_starters records actual starters |
| Confirmed lineups and batting order | lineup strength | Retrosheet box_starters & box_batting_lines, MLB live feed | Yes (4.1M starters, 5.7M batting lines) | Final yes, pregame snapshot yes | Pregame lineup posts hours before first pitch; need snapshots for live |
| Pitch-by-pitch results 2008+ | player skill, xwOBA, stuff | Statcast `pitches` (pitch data from 2008, tracking from 2015) | Yes (14,971,703 pitches 2008-2026) | Yes, with a cut-off date | Minor-league pitches separate (4,522,877 rows 2021-2026) |
| Play-by-play events (all years) | RE24, run values, base-out state | Retrosheet `events`, `events_deduced` | Yes (15,844,833 events + 278,885 deduced) | Yes | Deduced events fill the gaps in old seasons |
| Run expectancy / win probability tables | RE24, leverage | derived from Retrosheet events; MLB `game_win_probability` for cross-check | Yes (2,113,561 rows in game_win_probability) | Yes | Build per era, not one table for 150 years |
| Player history for projections (Marcel, PECOTA/ZiPS-like) | pre-season and in-season player forecasts | BRef WAR, FanGraphs, Lahman, Retrosheet daily splits, Statcast | Yes (184k BRef WAR, 1.2M FanGraphs, 5.2M splits, 210k Lahman) | Yes, with a cut-off date | Needs ages and birth dates (Chadwick register, Lahman People) |
| Player IDs and names | joining every source | Chadwick register | Yes (526,894 crosswalk register rows) | Yes | Unifies MLBAM, Retrosheet, BRef, FanGraphs, Lahman IDs |
| Bat tracking, arm strength, sprint speed, OAA, framing | skill beyond results | Statcast leaderboards | Yes (leaderboards 2015-2026 populated) | Prior seasons yes; same season no | Season level only, not per game |
| Park factors | park effect on runs | Statcast `leaderboard_park_factors`, FanGraphs, derived Retrosheet | Yes (Statcast 552 rows, FanGraphs 3,135 rows) | Prior seasons yes | Build our own rolling factor too |
| Weather: temperature, wind, sky, precipitation | run scoring, mostly for totals | Retrosheet game info (history); a weather source for forecasts | History yes (223k box_games); forecast no | History yes; forecast needs a snapshot | Missing source: pick a free historical weather service |
| Umpires | strike zone, totals | Retrosheet box_games, MLB `jobs_umpires` | Yes (223k box_games umpires, 98 in jobs_umpires) | Home plate umpire is announced pregame | Needs snapshot for live use |
| Rest, travel, doubleheaders, day/night | fatigue | derived from schedule plus venue coordinates | Derived, not built | Yes | Venue latitude/longitude come from MLB venues |
| Injuries, IL moves, call-ups | who is actually available | MLB `transactions`, rosters | To ingest | Yes if stamped by date | Need daily roster snapshots for backtests |
| Bullpen usage and fatigue | late-game strength | derived from boxscores and pitch counts per day | Derived, not built | Yes | |
| Team strength rating (Elo or similar) | simple strong baseline | derived from results | Derived, not built | Yes | Also the benchmark every complex model must beat |
| Standings | context only | MLB standings | To ingest | Only the day-before snapshot | Mostly redundant with results |
| **Kalshi market prices, history** | the thing we compare against | Kalshi public market API (candlesticks & trades) | **Yes** (110,994,885 trades, 14,903,320 candlesticks, 900,555 markets) | Yes, if stamped | Ingested into lake |
| **Polymarket market prices, history** | the same | Polymarket public price-history API | **Yes** (233,923 markets, 467,846 outcomes, 11,653 events) | Yes, if stamped | Ingested into lake; hourly price history pending |
| **Sportsbook closing lines** | the sharpest benchmark | paid or limited sources | **No** | Yes | Decision D3 |
| Fees and rules of each market | real profit after costs | exchange rule pages | **No** | n/a | Written down by hand, checked by the owner |

## Missing sources, plainly
1. Timestamped pregame snapshots (probable pitchers, lineups, umpires, active rosters): can only be collected going forward from now, so starting the collector early gives us history sooner. For past seasons we approximate with final starting lineups from Retrosheet `box_starters` and `box_games`.
2. Weather forecasts: need a free historical and live weather forecast source (e.g. Open-Meteo) for game-time temperature, wind, humidity, and precipitation.
3. Closing lines from sportsbooks: benchmark odds from books (Decision D3).
4. Local lake sync: ingest default MLB schedule, standings, and transactions to match homelab lake copy.

## Decisions for the owner (grilling, task 1.2)
- D1 Start the snapshot collector now, even before models exist? **Decided: YES (Option A).** Build scheduled pregame snapshot collector for announced lineups, probable pitchers, umpires, and weather.
- D2 Which seasons do models train on? (Pitch tracking era 2015+ for pitch skill; 2008+ for events with Statcast; older Retrosheet for run values.)
- D3 Pay for historical sportsbook lines, or use only the two exchanges?
- D4 Store the optional MLB sets (game feeds, boxscores, per-person stats) on this PC or the homelab?
- D5 Weather source choice.
- D6 Paper trading period before any real money, and the rule that I never place orders.

## Not in scope
Placing orders. Totals, props and season markets (later; same data plus run-scoring pieces). Legal and tax questions (the owner checks those).

## Findings: how far back market prices go (probed 2026-11-05, public endpoints, no login)

- **Kalshi** (`api.elections.kalshi.com/trade-api/v2`): game-winner series `KXMLBGAME`. `/historical/markets` lists 8,702 settled game markets; the oldest opened 2025-04-16 (`KXMLBGAME-25APR16AZMIA-MIA`). So about two seasons at most (2025 and 2026), one market per team per game. `/historical/markets/{ticker}/candlesticks?start_ts&end_ts&period_interval=60` gave hourly bid, ask, last price, volume and open interest for a one-day window. A very wide window returned HTTP 400, so ask one game at a time. Early-day volume is small (about 20 contracts), game-time volume is hundreds. Live and archived markets are split at `/historical/cutoff` (2026-09-06 for settled markets), so a downloader must read both.
- **Polymarket** (`gamma-api.polymarket.com` for events, `clob.polymarket.com/prices-history` for prices): the oldest closed MLB-tagged event found is 2024-09-26. `prices-history` with `interval=max` returned nothing for a closed market; with explicit `startTs`/`endTs` and `fidelity=60` it returned points (11 for a thin market). Tag coverage before Sept 2024 not checked.
- **Meaning:** market comparison is possible for about two seasons (Kalshi) and a little over two (Polymarket). Models train on the many older seasons; the market test is a short window. Thin early-day volume means only prices near first pitch should be trusted.
- **Not yet checked:** pregame lineups and probable pitchers in MLB's time-stamped game feed for old games.

## Findings: pregame lineups and probable pitchers for old games (probed 2026-11-05, small sample)

- `/v1/schedule?hydrate=probablePitcher,lineups` returns both probable pitchers and lineups for 2012, 2016, 2019 and 2024 sample days (15 of 15 games, 14 of 15 lineups in 2024). It is the state as of the call, so it shows who actually started. It is a stand-in, not an as-of snapshot.
- The time-stamped game feed (`/v1.1/game/{pk}/feed/live/timestamps`, then `?timecode=`) in 2019: the first stamp was 77 minutes or more before first pitch in the three games tried, state `Preview`, with probable pitchers and a nine-man batting order for each team. Usable as a real pregame snapshot. In 2013 the first stamp was after the game started (`Live`), so 2013 is not as-of safe. Which seasons are safe is unknown: a sweep over many games per season is needed (new task).
- Plan: use the first feed stamp that is before first pitch when it exists, the actual starters (Retrosheet, boxscore) when it does not, and keep a column that says which one was used.
