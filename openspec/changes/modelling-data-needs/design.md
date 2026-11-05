# Design: data needs for the game-winner model

Status of the "Have" column: written from the source docs and the dataset registry, **not yet verified against the lake** (task 1.1). "As of" means safe to use before first pitch in a backtest.

## The one rule that matters: as-of safety
A model may only use facts that were known before the game started. Final box scores, final standings, season totals and Savant leaderboards for the same season are NOT as-of safe for games inside that season. Features are built from a rolling cut-off date. Anything without a timestamp is treated as unsafe until proven otherwise.

## Field list

| Need | Used for | Source | Have? | As-of safe? | Notes |
|---|---|---|---|---|---|
| Game schedule, teams, venue, start time, doubleheader flag, final score | the label and the base table | MLB `/v1/schedule`, Retrosheet gamelogs | Yes | Schedule yes; score is the label only | Retrosheet gamelogs tie out MLB since 1871 |
| Probable starting pitchers | starter quality, the biggest single input | MLB schedule `hydrate=probablePitcher` | To verify | Only with a snapshot time | Needs timestamped snapshots, a later feed overwrites it |
| Confirmed lineups and batting order | lineup strength | MLB live feed / boxscore | Final lineups yes; pregame snapshots no | Final no, pregame snapshot yes | Pregame lineup posts hours before first pitch; need snapshots |
| Pitch-by-pitch results 2008+ | player skill, xwOBA, stuff | Statcast `pitches` (pitch data from 2008, tracking from 2015) | Yes | Yes, with a cut-off date | Minor-league pitches are separate |
| Play-by-play events (all years) | RE24, run values, base-out state | Retrosheet `events`, `events_deduced` | Yes | Yes | Deduced events fill the gaps in old seasons |
| Run expectancy / win probability tables | RE24, leverage | derived from Retrosheet events; MLB `game_win_probability` for cross-check | Derived, not built | Yes | Build per era, not one table for 150 years |
| Player history for projections (Marcel, PECOTA/ZiPS-like) | pre-season and in-season player forecasts | Lahman (checks), Retrosheet daily splits, MLB per-person stats, Statcast | Mostly yes | Yes, with a cut-off date | Needs ages and birth dates (Chadwick register, Lahman People) |
| Player IDs and names | joining every source | Chadwick register | Yes | Yes | |
| Bat tracking, arm strength, sprint speed, OAA, framing | skill beyond results | Statcast leaderboards | Yes (leaderboards are season level) | Prior seasons yes; same season no | Season level only, not per game |
| Park factors | park effect on runs | Statcast `leaderboard_park_factors`, derived from Retrosheet | Yes / derived | Prior seasons yes | Build our own rolling factor too |
| Weather: temperature, wind, sky, precipitation | run scoring, mostly for totals | Retrosheet game info (history); a weather source for forecasts | History partly; forecast no | History yes; forecast needs a snapshot | Missing source: pick a free historical weather service |
| Umpires | strike zone, totals | Retrosheet, MLB `jobs_umpires` | Yes | Home plate umpire is announced pregame | Needs snapshot for live use |
| Rest, travel, doubleheaders, day/night | fatigue | derived from schedule plus venue coordinates | Derived, not built | Yes | Venue latitude/longitude come from MLB venues |
| Injuries, IL moves, call-ups | who is actually available | MLB `transactions`, rosters | Yes (transactions) | Yes if stamped by date | Need daily roster snapshots for backtests |
| Bullpen usage and fatigue | late-game strength | derived from boxscores and pitch counts per day | Derived, not built | Yes | |
| Team strength rating (Elo or similar) | simple strong baseline | derived from results | Derived, not built | Yes | Also the benchmark every complex model must beat |
| Standings | context only | MLB standings | Yes | Only the day-before snapshot | Mostly redundant with results |
| **Kalshi market prices, history** | the thing we compare against | Kalshi public market API (candlesticks) | **No** | Yes, if stamped | New source |
| **Polymarket market prices, history** | the same | Polymarket public price-history API | **No** | Yes, if stamped | New source |
| **Sportsbook closing lines** | the sharpest benchmark | paid or limited sources | **No** | Yes | Decision D3 |
| Fees and rules of each market | real profit after costs | exchange rule pages | **No** | n/a | Written down by hand, checked by the owner |

## Missing sources, plainly
1. Market price history (Kalshi, Polymarket): must be downloaded before models can be judged at all, because a model is only useful if it beats the price.
2. Timestamped snapshots (probable pitchers, lineups, umpires, rosters): can only be collected going forward from now, so starting the collector early gives us history sooner. For past seasons we approximate with final data and say so.
3. Weather.
4. Closing lines from sportsbooks.

## Decisions for the owner (grilling, task 1.2)
- D1 Start the snapshot collector now, even before models exist? (My pick: yes, it is cheap and cannot be recreated later.)
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
