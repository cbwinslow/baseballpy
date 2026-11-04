# Master Baseball Dataset Coverage Matrix

This document provides an exhaustive catalog of all baseball datasets across the public data
ecosystem, comparing `baseballpy` against `pybaseball`, `baseballr`, `MLB-StatsAPI`, and the
official MLB OpenAPI specification.

- **Total Registered Datasets in baseballpy:** 459
- **MLB Stats API:** 365 datasets across 65 API routes
- **Statcast (Baseball Savant):** 38 datasets (MLB pitches, Minor League pitches, 36 leaderboards)
- **Retrosheet:** 25 datasets (PBP events, game logs, boxscores, rosters)
- **Lahman Database:** 27 datasets (complete historical database 1871–present)
- **Chadwick Bureau:** 4 datasets (universal player ID crosswalk)

---

## 1. Cross-Tool Capability Comparison

| Domain | Capability / Feature | `pybaseball` | `baseballr` | `MLB-StatsAPI` | `baseballpy` Status | Data Origin & Notes |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **MLB Stats API** | Live Game Feed & Events | - | mlb_pbp() | get_game() | **Supported** (`mlb_api:game_feed_plays, stream_live_events()`) | Real-time event streaming with watermarking, monotonic index, and snapshot projections. |
| **MLB Stats API** | Boxscores & Linescores | - | mlb_boxscore(), mlb_game_linescore() | get_game_boxscore(), get_game_linescore() | **Supported** (`mlb_api:game_boxscore_*, game_linescore, get_boxscore()`) | Batting, pitching, fielding boxscores and inning-by-inning linescores. |
| **MLB Stats API** | Schedule (Hydrated) | - | mlb_schedule() | get_schedule() | **Supported** (`mlb_api:schedule_hydrated, get_schedule()`) | Full season schedules with probable pitchers, venue info, and broadcast metadata. |
| **MLB Stats API** | Standings | standings() (B-Ref) | mlb_standings() | get_standings() | **Supported** (`mlb_api:standings_*, get_standings()`) | Regular season, wild card, division leaders, spring training, and postseason standings. |
| **MLB Stats API** | Rosters & Teams | - | mlb_rosters(), mlb_teams() | get_team_roster(), get_teams() | **Supported** (`mlb_api:team_roster_*, teams_season, get_roster(), get_teams()`) | Active, 40-man, depth chart, non-roster invitees, and coaching staff across MLB and 20 minor leagues. |
| **MLB Stats API** | Player & Team Situational Splits | - | Partial | get_person_stats() | **Supported** (`mlb_api:stats_stat_splits_*, people_stats_* (160+ tables)`) | Direct route refused 406 since Oct 2026; baseballpy uses automated player-level hydrate fallback. |
| **MLB Stats API** | Draft History & Prospects | - | mlb_draft(), mlb_draft_prospects() | get_draft() | **Supported** (`mlb_api:draft_picks, draft_prospects, get_draft()`) | Complete rule 4 draft selections and scout prospect rankings. |
| **MLB Stats API** | Transactions & Free Agents | - | mlb_transactions() | get_transactions() | **Supported** (`mlb_api:transactions_season, free_agents, get_transactions()`) | Historical trades, waivers, assignments, injured list movements, and signings. |
| **MLB Stats API** | Awards & Honors | - | - | get_awards() | **Supported** (`mlb_api:award_recipients, ref_awards`) | All MVP, Cy Young, Rookie of the Year, Gold Glove, and Silver Slugger recipients. |
| **MLB Stats API** | Reference Dictionaries & Lookup Tables | - | - | Partial | **Supported** (`mlb_api:ref_* (35 reference tables)`) | Sports, leagues, divisions, job types, pitch codes, event types, venues, and situation codes. |
| **Statcast** | Major League Pitch Tracking | statcast(), statcast_pitcher(), statcast_batter() | statcast_search(), statcast_search_batters() | - | **Supported** (`statcast:pitches, statcast()`) | Full 120-column physical pitch trajectory, release point, spin, exit velo, and launch angle. |
| **Statcast** | Minor League Pitch Tracking (Triple-A) | - | - | - | **Supported** (`statcast:pitches_minors`) | Triple-A Statcast tracking data (available since 2023). |
| **Statcast** | Exit Velocity & Barrels Leaderboard | statcast_pitcher_exitvelo_barrels() | statcast_leaderboards(type='exit_velocity') | - | **Supported** (`statcast:leaderboard_exit_velocity_barrels`) | Hard hit rate, max exit velo, barrels per plate appearance and batted ball event. |
| **Statcast** | Expected Statistics (xBA, xSLG, xwOBA) | statcast_batter_expected_stats() | statcast_leaderboards(type='expected_statistics') | - | **Supported** (`statcast:leaderboard_expected_statistics`) | Quality of contact expected metrics for batters and pitchers. |
| **Statcast** | Sprint Speed & Running Splits | statcast_sprint_speed(), statcast_running_splits() | statcast_leaderboards(type='sprint_speed') | - | **Supported** (`statcast:leaderboard_sprint_speed, running_splits`) | Ft/sec sprint speeds, 90-foot splits, and runner bolt metrics. |
| **Statcast** | Pitch Arsenals & Movement | statcast_pitcher_pitch_arsenal(), statcast_pitcher_arsenal_stats() | statcast_leaderboards(type='pitch_arsenal') | - | **Supported** (`statcast:leaderboard_pitch_arsenals, pitch_movement`) | Pitch type breakdown, velocity, active spin rate, and horizontal/vertical break. |
| **Statcast** | Outs Above Average & Catch Probability | statcast_outfield_directional_outs_above_average() | statcast_leaderboards(type='outs_above_average') | - | **Supported** (`statcast:leaderboard_outs_above_average, catch_probability`) | Directional infield and outfield defensive range and catch difficulty metrics. |
| **Statcast** | Catcher Pop Time & Framing | statcast_catcher_poptime() | statcast_leaderboards(type='poptime') | - | **Supported** (`statcast:leaderboard_catcher_poptime, catcher_framing`) | Exchange time, 2B throw time, arm strength, and strike zone framing strike rate. |
| **Statcast** | Bat Tracking (Swing Path & Speed) | - | statcast_leaderboards(type='bat_tracking') | - | **Supported** (`statcast:leaderboard_bat_tracking`) | New in 2024: bat speed (mph), swing length (ft), squared-up rate, and blast rate. |
| **Statcast** | Arm Strength | - | statcast_leaderboards(type='arm_strength') | - | **Supported** (`statcast:leaderboard_arm_strength`) | Maximum throwing velocity for outfielders and infielders on competitive throws. |
| **Statcast** | Pitch Tempo | - | statcast_leaderboards(type='pitch_tempo') | - | **Supported** (`statcast:leaderboard_pitch_tempo`) | Median seconds between pitches with bases empty and runners on base. |
| **Retrosheet** | Play-by-Play Event Files (.EVA/.EVN) | - | retrosheet_data() | - | **Supported** (`retrosheet:events, events()`) | Complete historical event logs covering pitches, pickoffs, and plays back to 1914. |
| **Retrosheet** | Game Logs | - | - | - | **Supported** (`retrosheet:game_logs, postseason_game_logs, game_logs()`) | Official game summary lines with 161 columns for every major league game from 1871-present. |
| **Retrosheet** | Box Scores & Accounts | - | - | - | **Supported** (`retrosheet:boxscores, box_records, boxscores()`) | Player box scores, lineup batting orders, and daily game accounts. |
| **Retrosheet** | Rosters & Substitutions | - | - | - | **Supported** (`retrosheet:rosters, substitutions, rosters()`) | In-game substitution sequences and seasonal roster files. |
| **Retrosheet** | Daily Splits | - | - | - | **Supported** (`retrosheet:daily_splits, daily_splits()`) | Day-by-day split accumulations for batting and pitching. |
| **Lahman** | Historical Player Stats (Batting, Pitching, Fielding) | batting(), pitching(), fielding() | - | - | **Supported** (`lahman:Batting, Pitching, Fielding, batting(), pitching(), fielding()`) | Standard historical database tables partitioned 1871-present. |
| **Lahman** | Teams & Franchises | teams() | - | - | **Supported** (`lahman:Teams, TeamsFranchises, teams()`) | Historical team records, attendance, home runs, and franchise lineage. |
| **Lahman** | Biographical People & Hall of Fame | people() | - | - | **Supported** (`lahman:People, HallOfFame, people(), hall_of_fame()`) | Player birth dates, debut dates, batting/throwing hands, and Hall of Fame voting records. |
| **Lahman** | Salaries, Awards & All-Star Games | salaries(), allstar() | - | - | **Supported** (`lahman:Salaries, AwardsPlayers, AllstarFull, salaries(), allstar()`) | Historical player salary figures (1985-present), award voting, and All-Star rosters. |
| **Chadwick** | Player ID Crosswalk / Resolution | playerid_lookup(), chadwick_register() | chadwick_player_lu() | - | **Supported** (`chadwick:register, resolve_player(), crosswalk()`) | Universal cross-reference linking MLBAM ID, Retrosheet ID, Baseball-Reference slug, and FanGraphs ID. |
| **Chadwick** | Aliases, Leagues & Country Codes | - | - | - | **Supported** (`chadwick:register_names, register_leagues, register_countries`) | Nicknames, alternative spellings, historical league codes, and country mappings. |
| **FanGraphs (Scraped)** | Advanced Batting Metrics (wOBA, wRC+, WAR) | batting_stats(), team_batting() | fg_batter_leaders(), fg_team_batter() | - | *Derived / Not Scraped* (`Derived: Compute from Statcast / Retrosheet / Lahman`) | FanGraphs scrapes violate TOS and break on HTML changes. Underlying raw event and pitch data are fully ingested in baseballpy. |
| **FanGraphs (Scraped)** | Advanced Pitching Metrics (FIP, xFIP, SIERA) | pitching_stats(), team_pitching() | fg_pitcher_leaders(), fg_team_pitcher() | - | *Derived / Not Scraped* (`Derived: Compute from Statcast / Retrosheet / Lahman`) | FIP and run-prevention metrics are deterministically calculable from Statcast and Lahman pitching data. |
| **Baseball-Reference (Scraped)** | Daily Player Game Logs & Splits | bref_daily_batter(), bref_daily_pitcher() | bref_daily_batter(), bref_daily_pitcher() | - | **Supported via Official Feeds** (`retrosheet:daily_splits, mlb_api:team_stats_by_date_range_*`) | Baseball-Reference scrapes are rate-limited by Cloudflare. baseballpy provides identical daily splits from Retrosheet and MLB API. |
| **NCAA / College (Scraped)** | NCAA College Baseball Scraping | - | ncaa_scrape() | - | **Partially Supported** (`lahman:CollegePlaying`) | College player history is in Lahman CollegePlaying; live NCAA college pitch tracking is outside professional MLB scope. |

---

## 2. Ingestion Architecture: Why We Avoid Unofficial Web Scraping

`pybaseball` and `baseballr` scrape HTML pages from **FanGraphs** and **Baseball-Reference**.
While convenient for quick ad-hoc analysis, web scraping introduces severe production risks:
1. **IP Bans & Cloudflare Blocks:** Scraping HTML triggers HTTP 429 and CAPTCHAs, breaking automated pipelines.
2. **Fragile DOM Selectors:** HTML class changes cause silent parser failures and corrupted schemas.
3. **Zero Added Value:** Both FanGraphs and Baseball-Reference derive their core metrics from the exact same raw data:
   - **Statcast Pitches:** Full pitch tracking data from Baseball Savant (`baseballpy.sources.statcast`).
   - **Retrosheet Play-by-Play:** Historical events, box scores, and game logs (`baseballpy.sources.retrosheet`).
   - **MLB Stats API:** Official real-time scoring, rosters, and schedules (`baseballpy.sources.mlb_api`).

`baseballpy` ingests the **authoritative raw feeds** with zero-copy PyArrow schemas, allowing analysts to compute
or train any derived sabermetric metric without web scraping dependencies.

---

## 3. Exhaustive Catalog of All Registered Datasets in `baseballpy`

### STATCAST (38 datasets)

| Dataset Name | View Name | Partition | Columns | Primary Keys | Description |
| :--- | :--- | :--- | :---: | :--- | :--- |
| `leaderboard_abs_challenges` | `statcast_leaderboard_abs_challenges` | `none` | 56 | `entity_name`, `team_abbr`, `year`, `level` | Automated ball-strike challenge system results per player (2025+; empty before). |
| `leaderboard_active_spin` | `statcast_leaderboard_active_spin` | `season` | 13 | `entity_id`, `pitch_hand` | Active spin (measured vs inferred) per pitcher and pitch type; the `min` qualifier breaks this route, so it is not sent. |
| `leaderboard_arm_strength` | `statcast_leaderboard_arm_strength` | `season` | 27 | `player_id` | Fielder arm strength (max and per-base average) per player-season. |
| `leaderboard_baserunning` | `statcast_leaderboard_baserunning` | `season` | 22 | `entity_id`, `year` | Extra-base-taken baserunning run value per runner-season. |
| `leaderboard_baserunning_run_value` | `statcast_leaderboard_baserunning_run_value` | `season` | 19 | `player_id`, `start_year`, `end_year` | Baserunning run value breakdown (extra bases, steal-of-base, swipe/snipe/freeze). |
| `leaderboard_basestealing_run_value` | `statcast_leaderboard_basestealing_run_value` | `season` | 25 | `player_id`, `start_year`, `end_year`, `key_target_base` | Base-stealing run value and lead metrics by target base. |
| `leaderboard_bat_tracking` | `statcast_leaderboard_bat_tracking` | `season` | 19 | `id` | Bat speed, swing length, squared-up and blast rates per batter-season (2023+). |
| `leaderboard_batted_ball` | `statcast_leaderboard_batted_ball` | `season` | 19 | `id`, `year` | Batted-ball profile (pull/straight/oppo, ground/line/fly rates) per batter-season. |
| `leaderboard_catch_probability` | `statcast_leaderboard_catch_probability` | `season` | 19 | `player_id` | Fielder catch probability by star bucket (2016 onwards). The `type` parameter empties this route (and produced anonymous rows in an earlier probe), so it is not sent. |
| `leaderboard_catcher_blocking` | `statcast_leaderboard_catcher_blocking` | `season` | 18 | `player_id`, `start_year` | Catcher blocking runs and blocks above average per catcher-span. |
| `leaderboard_catcher_framing` | `statcast_leaderboard_catcher_framing` | `season` | 22 | `id` | Catcher framing runs by zone per catcher-season. |
| `leaderboard_exit_velocity_batter` | `statcast_leaderboard_exit_velocity_batter` | `season` | 19 | `player_id` | Exit velocity, launch angle and barrels per batter-season (batted-ball events). |
| `leaderboard_exit_velocity_batter_team` | `statcast_leaderboard_exit_velocity_batter_team` | `season` | 19 | `team_id` | Exit velocity and barrels per batting team-season. |
| `leaderboard_exit_velocity_pitcher` | `statcast_leaderboard_exit_velocity_pitcher` | `season` | 19 | `player_id` | Exit velocity, launch angle and barrels allowed per pitcher-season. |
| `leaderboard_exit_velocity_pitcher_team` | `statcast_leaderboard_exit_velocity_pitcher_team` | `season` | 19 | `team_id` | Exit velocity and barrels allowed per pitching team-season. |
| `leaderboard_expected_statistics_batter` | `statcast_leaderboard_expected_statistics_batter` | `season` | 15 | `player_id`, `year` | Expected stats (xBA, xSLG, xwOBA) per batter-season. |
| `leaderboard_expected_statistics_pitcher` | `statcast_leaderboard_expected_statistics_pitcher` | `season` | 18 | `player_id`, `year` | Expected stats (xBA, xSLG, xwOBA, xERA) per pitcher-season. |
| `leaderboard_fielding_run_value` | `statcast_leaderboard_fielding_run_value` | `season` | 28 | `id`, `team_id` | Fielding run value by fielder (embedded JSON rows of the page, no qualifier). |
| `leaderboard_home_runs` | `statcast_leaderboard_home_runs` | `season` | 14 | `player_id`, `year`, `type` | Home run tracking (no-doubters, expected home runs) per player-season. |
| `leaderboard_outfield_jump` | `statcast_leaderboard_outfield_jump` | `season` | 13 | `resp_fielder_id`, `year` | Outfielder jump (reaction, burst and routing distance) per fielder-season. |
| `leaderboard_outs_above_average` | `statcast_leaderboard_outs_above_average` | `season` | 17 | `player_id`, `year`, `primary_pos_formatted` | Outs Above Average (OAA) and fielding runs prevented per fielder-position-season. |
| `leaderboard_park_factors` | `statcast_leaderboard_park_factors` | `season` | 31 | `venue_id`, `key_year` | Statcast park factor indices per venue and 3-year span (embedded JSON on the page). |
| `leaderboard_percentile_rankings_batter` | `statcast_leaderboard_percentile_rankings_batter` | `season` | 24 | `player_id`, `year` | Statcast percentile inputs per batter-season. |
| `leaderboard_percentile_rankings_pitcher` | `statcast_leaderboard_percentile_rankings_pitcher` | `season` | 23 | `player_id`, `year` | Statcast percentile inputs per pitcher-season. |
| `leaderboard_pitch_arsenal_stats` | `statcast_leaderboard_pitch_arsenal_stats` | `season` | 21 | `player_id`, `pitch_type` | Results (run value, BA, SLG, wOBA, whiff%) per pitcher and pitch type. |
| `leaderboard_pitch_arsenals` | `statcast_leaderboard_pitch_arsenals` | `season` | 13 | `pitcher` | Average velocity per pitch type per pitcher-season (switch pitchers have one row per arm). |
| `leaderboard_pitch_clock` | `statcast_leaderboard_pitch_clock` | `season` | 11 | `entity_id`, `year` | Pitch-timer violations by kind per player-season (2023+). |
| `leaderboard_pitch_movement` | `statcast_leaderboard_pitch_movement` | `season` | 25 | `pitcher_id`, `pitch_type`, `pitch_hand` | Pitch movement (induced vertical and horizontal break) per pitcher and pitch type. |
| `leaderboard_pitch_tempo` | `statcast_leaderboard_pitch_tempo` | `season` | 14 | `entity_id` | Time between pitches (median seconds by situation) per pitcher-season. |
| `leaderboard_poptime` | `statcast_leaderboard_poptime` | `season` | 15 | `entity_id` | Catcher pop time and arm strength on steal attempts per catcher-season. |
| `leaderboard_rolling` | `statcast_leaderboard_rolling` | `none` | 26 | `player_id`, `cat`, `cat_bin` | Rolling last-N-batted-ball xwOBA windows (50/100/250) per batter and pitcher: a snapshot of the current season (the page ignores the season parameter). |
| `leaderboard_running_splits` | `statcast_leaderboard_running_splits` | `season` | 27 | `player_id`, `team_id`, `position_name`, `bat_side` | 90-foot running splits (time since contact at each 5-foot mark) per player-season. |
| `leaderboard_spin_direction_pitches` | `statcast_leaderboard_spin_direction_pitches` | `season` | 30 | `player_id`, `api_pitch_type` | Measured vs inferred spin direction and active spin per pitcher and pitch type. |
| `leaderboard_sprint_speed` | `statcast_leaderboard_sprint_speed` | `season` | 11 | `player_id` | Sprint speed (ft/s on competitive runs) per player-season. |
| `leaderboard_swing_path_attack_angle` | `statcast_leaderboard_swing_path_attack_angle` | `season` | 14 | `id`, `side` | Swing path: attack angle, attack direction and swing tilt per batter-season (2023+). |
| `leaderboard_swing_take` | `statcast_leaderboard_swing_take` | `season` | 12 | `player_id`, `year` | Swing/take run value by zone region per batter-season. |
| `pitches` | `statcast_pitches` | `season` | 120 | `game_pk`, `at_bat_number`, `pitch_number` | Pitch-level Statcast search results. |
| `pitches_minors` | `statcast_pitches_minors` | `season` | 120 | `game_pk`, `at_bat_number`, `pitch_number` | Minor-league pitch-level Statcast search results (minors=true, 2021 onwards). |

### MLB_API (365 datasets)

| Dataset Name | View Name | Partition | Columns | Primary Keys | Description |
| :--- | :--- | :--- | :---: | :--- | :--- |
| `award_recipients` | `mlb_award_recipients` | `season` | 17 | `id`, `season` | Recipients of every award for a season (one request per award id; several rows per award-season are normal). |
| `box_batting` | `mlb_box_batting` | `season` | 17 | `game_pk`, `team_id`, `player_id` | Official batting boxscore lines. |
| `box_pitching` | `mlb_box_pitching` | `season` | 13 | `game_pk`, `team_id`, `player_id` | Official pitching boxscore lines. |
| `divisions_season` | `mlb_divisions_season` | `season` | 16 | `id` | Divisions of a season. |
| `draft` | `mlb_draft` | `season` | 9 | `year`, `pick_overall` | First-year player draft picks. |
| `draft_picks` | `mlb_draft_picks` | `season` | 85 | `pick_number`, `pick_round` | Every pick of a draft year with the person, school, scouting and signing fields. |
| `draft_prospects` | `mlb_draft_prospects` | `season` | 106 | `person_id`, `year` | Draft prospects of a year. |
| `free_agents` | `mlb_free_agents` | `season` | 18 | `player_id` | Free agents of a season. |
| `game_boxscore_info` | `mlb_game_boxscore_info` | `season` | 4 | `game_pk`, `label` | Game info label/value lines (weather, attendance, venue, first pitch, ...). |
| `game_boxscore_officials` | `mlb_game_boxscore_officials` | `season` | 6 | `game_pk`, `official_type` | Umpires of a game from the boxscore. |
| `game_boxscore_pitching_notes` | `mlb_game_boxscore_pitching_notes` | `season` | 3 | `game_pk`, `value` | Pitching notes of a game (one text line each). |
| `game_boxscore_players` | `mlb_game_boxscore_players` | `season` | 609 | `game_pk`, `teams_key`, `person_id` | Every player line of a game boxscore (person, position, batting/pitching/fielding stats, season stats, game status) with its team context. |
| `game_boxscore_teams` | `mlb_game_boxscore_teams` | `season` | 303 | `game_pk`, `teams_key` | Team totals of a game boxscore (team, teamStats, batters/pitchers/bench/bullpen id lists and info as JSON). |
| `game_boxscore_top_performers` | `mlb_game_boxscore_top_performers` | `season` | 234 | `game_pk`, `type`, `player_person_id` | Top performers of a game from the boxscore. |
| `game_changes` | `mlb_game_changes` | `none` | 70 | `game_pk` | Games changed since a timestamp (incremental sync log; append-only). |
| `game_feed_linescore_innings` | `mlb_game_feed_linescore_innings` | `season` | 12 | `game_pk`, `num` | Inning-by-inning linescore from the live feed. |
| `game_feed_officials` | `mlb_game_feed_officials` | `season` | 6 | `game_pk`, `official_type` | Umpires of a final game from the live feed. |
| `game_feed_play_events` | `mlb_game_feed_play_events` | `season` | 155 | `game_pk`, `all_plays_about_at_bat_index`, `index` | Every pitch/action event of a final game (pitchData, hitData, details, count) with its plate appearance's context. |
| `game_feed_plays` | `mlb_game_feed_plays` | `season` | 60 | `game_pk`, `about_at_bat_index` | Every plate appearance of a final game from the live feed (result, about, count, matchup). |
| `game_linescore` | `mlb_game_linescore` | `season` | 12 | `game_pk`, `num` | Inning-by-inning linescore of a game. |
| `game_play_by_play` | `mlb_game_play_by_play` | `season` | 59 | `game_pk`, `at_bat_index` | Every play of a game (matchup, result, count, runners as JSON). |
| `game_win_probability` | `mlb_game_win_probability` | `season` | 67 | `game_pk`, `at_bat_index` | Win probability after every play. |
| `jobs_datacasters` | `mlb_jobs_datacasters` | `none` | 8 | `person_id` | Current datacasters (the upstream listing repeats some people, so the key is not unique). |
| `jobs_official_scorers` | `mlb_jobs_official_scorers` | `none` | 8 | `person_id` | Current official scorers (the upstream listing repeats some people, so the key is not unique). |
| `jobs_umpires` | `mlb_jobs_umpires` | `none` | 8 | `person_id` | Current umpire roster. |
| `leagues_season` | `mlb_leagues_season` | `season` | 42 | `id` | Leagues of a season. |
| `people_changes` | `mlb_people_changes` | `none` | 52 | `id` | People changed since a timestamp (incremental sync log; append-only). |
| `people_search` | `mlb_people_search` | `none` | 52 | `id` | People matching a name query (on demand). |
| `people_stats_available_stats_catching` | `mlb_people_stats_available_stats_catching` | `season` | 10 | `person_id` | Per-player catching stats, type availableStats (one request per person). |
| `people_stats_available_stats_fielding` | `mlb_people_stats_available_stats_fielding` | `season` | 10 | `person_id` | Per-player fielding stats, type availableStats (one request per person). |
| `people_stats_available_stats_game` | `mlb_people_stats_available_stats_game` | `season` | 10 | `person_id` | Per-player game stats, type availableStats (one request per person). |
| `people_stats_available_stats_hitting` | `mlb_people_stats_available_stats_hitting` | `season` | 10 | `person_id` | Per-player hitting stats, type availableStats (one request per person). |
| `people_stats_available_stats_pitching` | `mlb_people_stats_available_stats_pitching` | `season` | 10 | `person_id` | Per-player pitching stats, type availableStats (one request per person). |
| `people_stats_available_stats_running` | `mlb_people_stats_available_stats_running` | `season` | 10 | `person_id` | Per-player running stats, type availableStats (one request per person). |
| `people_stats_available_stats_streak` | `mlb_people_stats_available_stats_streak` | `season` | 10 | `person_id` | Per-player streak stats, type availableStats (one request per person). |
| `people_stats_available_stats_team` | `mlb_people_stats_available_stats_team` | `season` | 10 | `person_id` | Per-player team stats, type availableStats (one request per person). |
| `people_stats_by_date_range_advanced_catching` | `mlb_people_stats_by_date_range_advanced_catching` | `season` | 31 | `person_id`, `team_id`, `sport_id` | Per-player catching stats, type byDateRangeAdvanced (one request per person). |
| `people_stats_by_date_range_advanced_fielding` | `mlb_people_stats_by_date_range_advanced_fielding` | `season` | 44 | `person_id`, `team_id`, `sport_id`, `num_teams`, `stat_games_played` | Per-player fielding stats, type byDateRangeAdvanced (one request per person). |
| `people_stats_by_date_range_advanced_hitting` | `mlb_people_stats_by_date_range_advanced_hitting` | `season` | 30 | `person_id`, `team_id`, `sport_id` | Per-player hitting stats, type byDateRangeAdvanced (one request per person). |
| `people_stats_by_date_range_advanced_pitching` | `mlb_people_stats_by_date_range_advanced_pitching` | `season` | 38 | `person_id`, `team_id`, `sport_id` | Per-player pitching stats, type byDateRangeAdvanced (one request per person). |
| `people_stats_by_day_of_week_catching` | `mlb_people_stats_by_day_of_week_catching` | `season` | 46 | `person_id`, `team_id`, `sport_id`, `league_id`, `season`, `day_of_week` | Per-player catching stats, type byDayOfWeek (one request per person). |
| `people_stats_by_day_of_week_fielding` | `mlb_people_stats_by_day_of_week_fielding` | `season` | 41 | `person_id`, `team_id`, `sport_id`, `league_id`, `season`, `day_of_week` | Per-player fielding stats, type byDayOfWeek (one request per person). |
| `people_stats_by_day_of_week_hitting` | `mlb_people_stats_by_day_of_week_hitting` | `season` | 53 | `person_id`, `team_id`, `sport_id`, `league_id`, `season`, `day_of_week` | Per-player hitting stats, type byDayOfWeek (one request per person). |
| `people_stats_by_day_of_week_pitching` | `mlb_people_stats_by_day_of_week_pitching` | `season` | 80 | `person_id`, `team_id`, `sport_id`, `league_id`, `season`, `day_of_week` | Per-player pitching stats, type byDayOfWeek (one request per person). |
| `people_stats_by_month_catching` | `mlb_people_stats_by_month_catching` | `season` | 46 | `person_id`, `team_id`, `sport_id`, `league_id`, `season`, `month` | Per-player catching stats, type byMonth (one request per person). |
| `people_stats_by_month_fielding` | `mlb_people_stats_by_month_fielding` | `season` | 41 | `person_id`, `team_id`, `sport_id`, `league_id`, `season`, `month` | Per-player fielding stats, type byMonth (one request per person). |
| `people_stats_by_month_hitting` | `mlb_people_stats_by_month_hitting` | `season` | 53 | `person_id`, `team_id`, `sport_id`, `league_id`, `season`, `month` | Per-player hitting stats, type byMonth (one request per person). |
| `people_stats_by_month_pitching` | `mlb_people_stats_by_month_pitching` | `season` | 80 | `person_id`, `team_id`, `sport_id`, `league_id`, `season`, `month` | Per-player pitching stats, type byMonth (one request per person). |
| `people_stats_career_advanced_hitting` | `mlb_people_stats_career_advanced_hitting` | `season` | 50 | `person_id` | Per-player hitting stats, type careerAdvanced (one request per person). |
| `people_stats_career_advanced_pitching` | `mlb_people_stats_career_advanced_pitching` | `season` | 75 | `person_id` | Per-player pitching stats, type careerAdvanced (one request per person). |
| `people_stats_career_catching` | `mlb_people_stats_career_catching` | `season` | 47 | `person_id` | Per-player catching stats, type career (one request per person). |
| `people_stats_career_fielding` | `mlb_people_stats_career_fielding` | `season` | 51 | `person_id`, `player_id`, `sport_id`, `game_type`, `position_abbreviation` | Per-player fielding stats, type career (one request per person). |
| `people_stats_career_game` | `mlb_people_stats_career_game` | `season` | 24 | `person_id` | Per-player game stats, type career (one request per person). |
| `people_stats_career_hitting` | `mlb_people_stats_career_hitting` | `season` | 53 | `person_id` | Per-player hitting stats, type career (one request per person). |
| `people_stats_career_pitching` | `mlb_people_stats_career_pitching` | `season` | 81 | `person_id` | Per-player pitching stats, type career (one request per person). |
| `people_stats_career_playoffs_catching` | `mlb_people_stats_career_playoffs_catching` | `season` | 47 | `person_id` | Per-player catching stats, type careerPlayoffs (one request per person). |
| `people_stats_career_playoffs_fielding` | `mlb_people_stats_career_playoffs_fielding` | `season` | 51 | `person_id`, `player_id`, `sport_id`, `game_type`, `position_abbreviation` | Per-player fielding stats, type careerPlayoffs (one request per person). |
| `people_stats_career_playoffs_game` | `mlb_people_stats_career_playoffs_game` | `season` | 24 | `person_id` | Per-player game stats, type careerPlayoffs (one request per person). |
| `people_stats_career_playoffs_hitting` | `mlb_people_stats_career_playoffs_hitting` | `season` | 53 | `person_id` | Per-player hitting stats, type careerPlayoffs (one request per person). |
| `people_stats_career_playoffs_pitching` | `mlb_people_stats_career_playoffs_pitching` | `season` | 81 | `person_id` | Per-player pitching stats, type careerPlayoffs (one request per person). |
| `people_stats_career_regular_season_catching` | `mlb_people_stats_career_regular_season_catching` | `season` | 47 | `person_id` | Per-player catching stats, type careerRegularSeason (one request per person). |
| `people_stats_career_regular_season_fielding` | `mlb_people_stats_career_regular_season_fielding` | `season` | 51 | `person_id`, `player_id`, `sport_id`, `game_type`, `position_abbreviation` | Per-player fielding stats, type careerRegularSeason (one request per person). |
| `people_stats_career_regular_season_game` | `mlb_people_stats_career_regular_season_game` | `season` | 24 | `person_id` | Per-player game stats, type careerRegularSeason (one request per person). |
| `people_stats_career_regular_season_hitting` | `mlb_people_stats_career_regular_season_hitting` | `season` | 53 | `person_id` | Per-player hitting stats, type careerRegularSeason (one request per person). |
| `people_stats_career_regular_season_pitching` | `mlb_people_stats_career_regular_season_pitching` | `season` | 81 | `person_id` | Per-player pitching stats, type careerRegularSeason (one request per person). |
| `people_stats_career_stat_splits_fielding` | `mlb_people_stats_career_stat_splits_fielding` | `season` | 22 | `person_id`, `player_id`, `sport_id`, `game_type`, `split_code` | Per-player fielding stats, type careerStatSplits, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'}. |
| `people_stats_career_stat_splits_hitting` | `mlb_people_stats_career_stat_splits_hitting` | `season` | 59 | `person_id` | Per-player hitting stats, type careerStatSplits, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'}. |
| `people_stats_career_stat_splits_pitching` | `mlb_people_stats_career_stat_splits_pitching` | `season` | 88 | `person_id`, `player_id`, `sport_id`, `game_type`, `split_code`, `split_description`, `stat_ops` | Per-player pitching stats, type careerStatSplits, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'}. |
| `people_stats_career_stat_splits_running` | `mlb_people_stats_career_stat_splits_running` | `season` | 25 | `person_id` | Per-player running stats, type careerStatSplits, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'}. |
| `people_stats_expected_statistics_hitting` | `mlb_people_stats_expected_statistics_hitting` | `season` | 24 | `person_id` | Per-player hitting stats, type expectedStatistics (one request per person). |
| `people_stats_expected_statistics_pitching` | `mlb_people_stats_expected_statistics_pitching` | `season` | 20 | `person_id` | Per-player pitching stats, type expectedStatistics (one request per person). |
| `people_stats_game_log_catching` | `mlb_people_stats_game_log_catching` | `season` | 58 | `person_id`, `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `game_type`, `date` | Per-player catching stats, type gameLog (one request per person). |
| `people_stats_game_log_fielding` | `mlb_people_stats_game_log_fielding` | `season` | 61 | `person_id`, `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `game_type`, `date`, `opponent_id`, `game_game_pk`, `position_abbreviation` | Per-player fielding stats, type gameLog (one request per person). |
| `people_stats_game_log_hitting` | `mlb_people_stats_game_log_hitting` | `season` | 67 | `person_id`, `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `game_type`, `date`, `opponent_id`, `game_game_pk` | Per-player hitting stats, type gameLog (one request per person). |
| `people_stats_game_log_pitching` | `mlb_people_stats_game_log_pitching` | `season` | 93 | `person_id`, `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `game_type`, `date` | Per-player pitching stats, type gameLog (one request per person). |
| `people_stats_home_and_away_catching` | `mlb_people_stats_home_and_away_catching` | `season` | 35 | `person_id`, `season`, `stat_games_played` | Per-player catching stats, type homeAndAway (one request per person). |
| `people_stats_home_and_away_fielding` | `mlb_people_stats_home_and_away_fielding` | `season` | 30 | `person_id`, `season`, `stat_games_played` | Per-player fielding stats, type homeAndAway (one request per person). |
| `people_stats_home_and_away_hitting` | `mlb_people_stats_home_and_away_hitting` | `season` | 42 | `person_id`, `season`, `stat_games_played` | Per-player hitting stats, type homeAndAway (one request per person). |
| `people_stats_home_and_away_pitching` | `mlb_people_stats_home_and_away_pitching` | `season` | 69 | `person_id`, `season`, `stat_games_played` | Per-player pitching stats, type homeAndAway (one request per person). |
| `people_stats_hot_cold_zones_hitting` | `mlb_people_stats_hot_cold_zones_hitting` | `season` | 6 | `person_id`, `stat_name` | Per-player hitting stats, type hotColdZones (one request per person). |
| `people_stats_hot_cold_zones_pitching` | `mlb_people_stats_hot_cold_zones_pitching` | `season` | 6 | `person_id`, `stat_name` | Per-player pitching stats, type hotColdZones (one request per person). |
| `people_stats_last_x_games_catching` | `mlb_people_stats_last_x_games_catching` | `season` | 42 | `person_id`, `team_id`, `sport_id` | Per-player catching stats, type lastXGames (one request per person). |
| `people_stats_last_x_games_fielding` | `mlb_people_stats_last_x_games_fielding` | `season` | 44 | `person_id`, `team_id`, `sport_id`, `num_teams`, `stat_games_played` | Per-player fielding stats, type lastXGames (one request per person). |
| `people_stats_last_x_games_hitting` | `mlb_people_stats_last_x_games_hitting` | `season` | 49 | `person_id`, `team_id`, `sport_id` | Per-player hitting stats, type lastXGames (one request per person). |
| `people_stats_last_x_games_pitching` | `mlb_people_stats_last_x_games_pitching` | `season` | 76 | `person_id`, `team_id`, `sport_id` | Per-player pitching stats, type lastXGames (one request per person). |
| `people_stats_metric_averages_pitching` | `mlb_people_stats_metric_averages_pitching` | `season` | 27 | `person_id`, `metric`, `player_id`, `season`, `game_type`, `num_occurrences` | Per-player pitching stats, type metricAverages, parameters {'season': '{season}', 'metrics': '{metric}'}. |
| `people_stats_metric_log_pitching` | `mlb_people_stats_metric_log_pitching` | `season` | 109 | `person_id` | Per-player pitching stats, type metricLog, parameters {'season': '{season}', 'metrics': '{metric}'}. |
| `people_stats_opponents_faced_catching` | `mlb_people_stats_opponents_faced_catching` | `season` | 18 | `person_id`, `game_type`, `batter_id`, `pitcher_id` | Per-player catching stats, type opponentsFaced (one request per person). |
| `people_stats_opponents_faced_fielding` | `mlb_people_stats_opponents_faced_fielding` | `season` | 18 | `person_id`, `game_type`, `batter_id`, `pitcher_id` | Per-player fielding stats, type opponentsFaced (one request per person). |
| `people_stats_opponents_faced_hitting` | `mlb_people_stats_opponents_faced_hitting` | `season` | 21 | `person_id`, `game_type`, `pitcher_id` | Per-player hitting stats, type opponentsFaced (one request per person). |
| `people_stats_opponents_faced_pitching` | `mlb_people_stats_opponents_faced_pitching` | `season` | 21 | `person_id`, `game_type`, `batter_id` | Per-player pitching stats, type opponentsFaced (one request per person). |
| `people_stats_opponents_faced_running` | `mlb_people_stats_opponents_faced_running` | `season` | 18 | `person_id`, `game_type`, `pitcher_id`, `batter_id` | Per-player running stats, type opponentsFaced (one request per person). |
| `people_stats_outs_above_average_catching` | `mlb_people_stats_outs_above_average_catching` | `season` | 29 | `person_id` | Per-player catching stats, type outsAboveAverage (one request per person). |
| `people_stats_outs_above_average_fielding` | `mlb_people_stats_outs_above_average_fielding` | `season` | 29 | `person_id` | Per-player fielding stats, type outsAboveAverage (one request per person). |
| `people_stats_outs_above_average_game` | `mlb_people_stats_outs_above_average_game` | `season` | 29 | `person_id` | Per-player game stats, type outsAboveAverage (one request per person). |
| `people_stats_outs_above_average_hitting` | `mlb_people_stats_outs_above_average_hitting` | `season` | 29 | `person_id` | Per-player hitting stats, type outsAboveAverage (one request per person). |
| `people_stats_outs_above_average_pitching` | `mlb_people_stats_outs_above_average_pitching` | `season` | 29 | `person_id` | Per-player pitching stats, type outsAboveAverage (one request per person). |
| `people_stats_outs_above_average_running` | `mlb_people_stats_outs_above_average_running` | `season` | 29 | `person_id` | Per-player running stats, type outsAboveAverage (one request per person). |
| `people_stats_outs_above_average_streak` | `mlb_people_stats_outs_above_average_streak` | `season` | 29 | `person_id` | Per-player streak stats, type outsAboveAverage (one request per person). |
| `people_stats_outs_above_average_team` | `mlb_people_stats_outs_above_average_team` | `season` | 29 | `person_id` | Per-player team stats, type outsAboveAverage (one request per person). |
| `people_stats_pitch_arsenal_hitting` | `mlb_people_stats_pitch_arsenal_hitting` | `season` | 10 | `person_id`, `stat_average_speed` | Per-player hitting stats, type pitchArsenal (one request per person). |
| `people_stats_pitch_arsenal_pitching` | `mlb_people_stats_pitch_arsenal_pitching` | `season` | 10 | `person_id`, `stat_percentage` | Per-player pitching stats, type pitchArsenal (one request per person). |
| `people_stats_pitch_log_hitting` | `mlb_people_stats_pitch_log_hitting` | `season` | 58 | `person_id` | Per-player hitting stats, type pitchLog (one request per person). |
| `people_stats_pitch_log_pitching` | `mlb_people_stats_pitch_log_pitching` | `season` | 58 | `person_id` | Per-player pitching stats, type pitchLog (one request per person). |
| `people_stats_play_log_hitting` | `mlb_people_stats_play_log_hitting` | `season` | 58 | `person_id` | Per-player hitting stats, type playLog (one request per person). |
| `people_stats_play_log_pitching` | `mlb_people_stats_play_log_pitching` | `season` | 58 | `person_id` | Per-player pitching stats, type playLog (one request per person). |
| `people_stats_projected_hitting` | `mlb_people_stats_projected_hitting` | `season` | 57 | `person_id` | Per-player hitting stats, type projected (one request per person). |
| `people_stats_projected_pitching` | `mlb_people_stats_projected_pitching` | `season` | 56 | `person_id` | Per-player pitching stats, type projected (one request per person). |
| `people_stats_projected_zips2_yr_hitting` | `mlb_people_stats_projected_zips2_yr_hitting` | `season` | 61 | `person_id` | Per-player hitting stats, type projected_Zips2YR, parameters {}. |
| `people_stats_projected_zips2_yr_pitching` | `mlb_people_stats_projected_zips2_yr_pitching` | `season` | 60 | `person_id` | Per-player pitching stats, type projected_Zips2YR, parameters {}. |
| `people_stats_projected_zips3_yr_hitting` | `mlb_people_stats_projected_zips3_yr_hitting` | `season` | 61 | `person_id` | Per-player hitting stats, type projected_Zips3YR, parameters {}. |
| `people_stats_projected_zips3_yr_pitching` | `mlb_people_stats_projected_zips3_yr_pitching` | `season` | 60 | `person_id` | Per-player pitching stats, type projected_Zips3YR, parameters {}. |
| `people_stats_projected_zips_hitting` | `mlb_people_stats_projected_zips_hitting` | `season` | 61 | `person_id` | Per-player hitting stats, type projected_Zips, parameters {}. |
| `people_stats_projected_zips_pitching` | `mlb_people_stats_projected_zips_pitching` | `season` | 60 | `person_id` | Per-player pitching stats, type projected_Zips, parameters {}. |
| `people_stats_rankings_by_year_hitting` | `mlb_people_stats_rankings_by_year_hitting` | `season` | 44 | `person_id`, `player_id`, `team_id`, `league_id`, `season` | Per-player hitting stats, type rankingsByYear (one request per person). |
| `people_stats_rankings_by_year_pitching` | `mlb_people_stats_rankings_by_year_pitching` | `season` | 56 | `person_id`, `player_id`, `team_id`, `league_id`, `season` | Per-player pitching stats, type rankingsByYear (one request per person). |
| `people_stats_rankings_hitting` | `mlb_people_stats_rankings_hitting` | `season` | 44 | `person_id` | Per-player hitting stats, type rankings (one request per person). |
| `people_stats_rankings_pitching` | `mlb_people_stats_rankings_pitching` | `season` | 49 | `person_id` | Per-player pitching stats, type rankings (one request per person). |
| `people_stats_sabermetrics_fielding` | `mlb_people_stats_sabermetrics_fielding` | `season` | 28 | `person_id` | Per-player fielding stats, type sabermetrics (one request per person). |
| `people_stats_sabermetrics_hitting` | `mlb_people_stats_sabermetrics_hitting` | `season` | 35 | `person_id` | Per-player hitting stats, type sabermetrics (one request per person). |
| `people_stats_sabermetrics_multi_team_fielding` | `mlb_people_stats_sabermetrics_multi_team_fielding` | `season` | 26 | `person_id`, `player_id`, `sport_id`, `league_id`, `season`, `game_type`, `position_abbreviation` | Per-player fielding stats, type sabermetricsMultiTeam (one request per person). |
| `people_stats_sabermetrics_multi_team_hitting` | `mlb_people_stats_sabermetrics_multi_team_hitting` | `season` | 36 | `person_id` | Per-player hitting stats, type sabermetricsMultiTeam (one request per person). |
| `people_stats_sabermetrics_multi_team_pitching` | `mlb_people_stats_sabermetrics_multi_team_pitching` | `season` | 33 | `person_id` | Per-player pitching stats, type sabermetricsMultiTeam (one request per person). |
| `people_stats_sabermetrics_pitching` | `mlb_people_stats_sabermetrics_pitching` | `season` | 32 | `person_id` | Per-player pitching stats, type sabermetrics (one request per person). |
| `people_stats_season_advanced_hitting` | `mlb_people_stats_season_advanced_hitting` | `season` | 50 | `person_id` | Per-player hitting stats, type seasonAdvanced (one request per person). |
| `people_stats_season_advanced_pitching` | `mlb_people_stats_season_advanced_pitching` | `season` | 75 | `person_id` | Per-player pitching stats, type seasonAdvanced (one request per person). |
| `people_stats_season_catching` | `mlb_people_stats_season_catching` | `season` | 50 | `person_id` | Per-player catching stats, type season (one request per person). |
| `people_stats_season_fielding` | `mlb_people_stats_season_fielding` | `season` | 51 | `person_id`, `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `game_type`, `position_abbreviation` | Per-player fielding stats, type season (one request per person). |
| `people_stats_season_game` | `mlb_people_stats_season_game` | `season` | 23 | `person_id` | Per-player game stats, type season (one request per person). |
| `people_stats_season_hitting` | `mlb_people_stats_season_hitting` | `season` | 53 | `person_id` | Per-player hitting stats, type season (one request per person). |
| `people_stats_season_pitching` | `mlb_people_stats_season_pitching` | `season` | 81 | `person_id` | Per-player pitching stats, type season (one request per person). |
| `people_stats_spray_chart_hitting` | `mlb_people_stats_spray_chart_hitting` | `season` | 13 | `person_id` | Per-player hitting stats, type sprayChart (one request per person). |
| `people_stats_spray_chart_pitching` | `mlb_people_stats_spray_chart_pitching` | `season` | 13 | `person_id` | Per-player pitching stats, type sprayChart (one request per person). |
| `people_stats_stat_splits_advanced_fielding` | `mlb_people_stats_stat_splits_advanced_fielding` | `season` | 29 | `person_id`, `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `game_type`, `split_code` | Per-player fielding stats, type statSplitsAdvanced, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'}. |
| `people_stats_stat_splits_advanced_hitting` | `mlb_people_stats_stat_splits_advanced_hitting` | `season` | 51 | `person_id` | Per-player hitting stats, type statSplitsAdvanced, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'}. |
| `people_stats_stat_splits_advanced_pitching` | `mlb_people_stats_stat_splits_advanced_pitching` | `season` | 64 | `person_id` | Per-player pitching stats, type statSplitsAdvanced, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'}. |
| `people_stats_stat_splits_advanced_running` | `mlb_people_stats_stat_splits_advanced_running` | `season` | 32 | `person_id` | Per-player running stats, type statSplitsAdvanced, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'}. |
| `people_stats_stat_splits_fielding` | `mlb_people_stats_stat_splits_fielding` | `season` | 29 | `person_id`, `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `game_type`, `split_code` | Per-player fielding stats, type statSplits, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'}. |
| `people_stats_stat_splits_hitting` | `mlb_people_stats_stat_splits_hitting` | `season` | 66 | `person_id` | Per-player hitting stats, type statSplits, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'}. |
| `people_stats_stat_splits_pitching` | `mlb_people_stats_stat_splits_pitching` | `season` | 95 | `person_id` | Per-player pitching stats, type statSplits, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'}. |
| `people_stats_stat_splits_running` | `mlb_people_stats_stat_splits_running` | `season` | 32 | `person_id` | Per-player running stats, type statSplits, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'}. |
| `people_stats_stats_single_season_advanced_hitting` | `mlb_people_stats_stats_single_season_advanced_hitting` | `season` | 50 | `person_id` | Per-player hitting stats, type statsSingleSeasonAdvanced (one request per person). |
| `people_stats_stats_single_season_advanced_pitching` | `mlb_people_stats_stats_single_season_advanced_pitching` | `season` | 75 | `person_id` | Per-player pitching stats, type statsSingleSeasonAdvanced (one request per person). |
| `people_stats_stats_single_season_catching` | `mlb_people_stats_stats_single_season_catching` | `season` | 50 | `person_id` | Per-player catching stats, type statsSingleSeason (one request per person). |
| `people_stats_stats_single_season_fielding` | `mlb_people_stats_stats_single_season_fielding` | `season` | 51 | `person_id`, `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `game_type`, `position_abbreviation` | Per-player fielding stats, type statsSingleSeason (one request per person). |
| `people_stats_stats_single_season_game` | `mlb_people_stats_stats_single_season_game` | `season` | 23 | `person_id` | Per-player game stats, type statsSingleSeason (one request per person). |
| `people_stats_stats_single_season_hitting` | `mlb_people_stats_stats_single_season_hitting` | `season` | 53 | `person_id` | Per-player hitting stats, type statsSingleSeason (one request per person). |
| `people_stats_stats_single_season_pitching` | `mlb_people_stats_stats_single_season_pitching` | `season` | 81 | `person_id` | Per-player pitching stats, type statsSingleSeason (one request per person). |
| `people_stats_vs_player5_y_hitting_opp_player` | `mlb_people_stats_vs_player5_y_hitting_opp_player` | `season` | 54 | `person_id` | Per-player hitting stats, type vsPlayer5Y, parameters {'season': '{season}', 'opposingPlayerId': '{opposing_player_id}'}. |
| `people_stats_vs_player5_y_hitting_opp_team` | `mlb_people_stats_vs_player5_y_hitting_opp_team` | `season` | 54 | `person_id`, `opposing_team_id`, `team_id`, `game_type`, `opponent_id`, `num_teams`, `pitcher_id` | Per-player hitting stats, type vsPlayer5Y, parameters {'season': '{season}', 'opposingTeamId': '{opposing_team_id}'}. |
| `people_stats_vs_player5_y_pitching_opp_team` | `mlb_people_stats_vs_player5_y_pitching_opp_team` | `season` | 67 | `person_id`, `opposing_team_id`, `team_id`, `game_type`, `opponent_id`, `num_teams`, `batter_id` | Per-player pitching stats, type vsPlayer5Y, parameters {'season': '{season}', 'opposingTeamId': '{opposing_team_id}'}. |
| `people_stats_vs_player_hitting_opp_player` | `mlb_people_stats_vs_player_hitting_opp_player` | `season` | 55 | `person_id`, `opposing_player_id`, `game_type`, `num_teams`, `stat_ops`, `stat_number_of_pitches` | Per-player hitting stats, type vsPlayer, parameters {'season': '{season}', 'opposingPlayerId': '{opposing_player_id}'}. |
| `people_stats_vs_player_hitting_opp_team` | `mlb_people_stats_vs_player_hitting_opp_team` | `season` | 55 | `person_id`, `opposing_team_id`, `game_type`, `opponent_id`, `num_teams`, `batter_id`, `pitcher_id`, `season` | Per-player hitting stats, type vsPlayer, parameters {'season': '{season}', 'opposingTeamId': '{opposing_team_id}'}. |
| `people_stats_vs_player_pitching_opp_team` | `mlb_people_stats_vs_player_pitching_opp_team` | `season` | 68 | `person_id`, `opposing_team_id`, `game_type`, `opponent_id`, `num_teams`, `batter_id`, `pitcher_id`, `season` | Per-player pitching stats, type vsPlayer, parameters {'season': '{season}', 'opposingTeamId': '{opposing_team_id}'}. |
| `people_stats_vs_player_running_opp_player` | `mlb_people_stats_vs_player_running_opp_player` | `season` | 33 | `person_id` | Per-player running stats, type vsPlayer, parameters {'season': '{season}', 'opposingPlayerId': '{opposing_player_id}'}. |
| `people_stats_vs_player_total_hitting_opp_player` | `mlb_people_stats_vs_player_total_hitting_opp_player` | `season` | 48 | `person_id` | Per-player hitting stats, type vsPlayerTotal, parameters {'season': '{season}', 'opposingPlayerId': '{opposing_player_id}'}. |
| `people_stats_vs_player_total_hitting_opp_team` | `mlb_people_stats_vs_player_total_hitting_opp_team` | `season` | 46 | `person_id` | Per-player hitting stats, type vsPlayerTotal, parameters {'season': '{season}', 'opposingTeamId': '{opposing_team_id}'}. |
| `people_stats_vs_player_total_pitching_opp_team` | `mlb_people_stats_vs_player_total_pitching_opp_team` | `season` | 59 | `person_id` | Per-player pitching stats, type vsPlayerTotal, parameters {'season': '{season}', 'opposingTeamId': '{opposing_team_id}'}. |
| `people_stats_vs_player_total_running_opp_player` | `mlb_people_stats_vs_player_total_running_opp_player` | `season` | 14 | `person_id`, `opposing_player_id`, `game_type`, `num_teams`, `pitcher_id` | Per-player running stats, type vsPlayerTotal, parameters {'season': '{season}', 'opposingPlayerId': '{opposing_player_id}'}. |
| `people_stats_vs_team5_y_hitting_opp_player` | `mlb_people_stats_vs_team5_y_hitting_opp_player` | `season` | 54 | `person_id` | Per-player hitting stats, type vsTeam5Y, parameters {'season': '{season}', 'opposingPlayerId': '{opposing_player_id}'}. |
| `people_stats_vs_team5_y_hitting_opp_team` | `mlb_people_stats_vs_team5_y_hitting_opp_team` | `season` | 60 | `person_id`, `opposing_team_id`, `team_id`, `season`, `game_type`, `opponent_id`, `rank`, `pitcher_id` | Per-player hitting stats, type vsTeam5Y, parameters {'season': '{season}', 'opposingTeamId': '{opposing_team_id}'}. |
| `people_stats_vs_team_hitting_opp_team` | `mlb_people_stats_vs_team_hitting_opp_team` | `season` | 65 | `person_id` | Per-player hitting stats, type vsTeam, parameters {'season': '{season}', 'opposingTeamId': '{opposing_team_id}'}. |
| `people_stats_vs_team_total_hitting_opp_player` | `mlb_people_stats_vs_team_total_hitting_opp_player` | `season` | 48 | `person_id` | Per-player hitting stats, type vsTeamTotal, parameters {'season': '{season}', 'opposingPlayerId': '{opposing_player_id}'}. |
| `people_stats_vs_team_total_hitting_opp_team` | `mlb_people_stats_vs_team_total_hitting_opp_team` | `season` | 60 | `person_id` | Per-player hitting stats, type vsTeamTotal, parameters {'season': '{season}', 'opposingTeamId': '{opposing_team_id}'}. |
| `people_stats_vs_team_total_running_opp_player` | `mlb_people_stats_vs_team_total_running_opp_player` | `season` | 14 | `person_id`, `opposing_player_id`, `game_type`, `num_teams`, `pitcher_id` | Per-player running stats, type vsTeamTotal, parameters {'season': '{season}', 'opposingPlayerId': '{opposing_player_id}'}. |
| `people_stats_win_loss_catching` | `mlb_people_stats_win_loss_catching` | `season` | 35 | `person_id`, `season`, `stat_games_played` | Per-player catching stats, type winLoss (one request per person). |
| `people_stats_win_loss_fielding` | `mlb_people_stats_win_loss_fielding` | `season` | 30 | `person_id`, `season`, `stat_games_played` | Per-player fielding stats, type winLoss (one request per person). |
| `people_stats_win_loss_hitting` | `mlb_people_stats_win_loss_hitting` | `season` | 42 | `person_id`, `season`, `stat_games_played` | Per-player hitting stats, type winLoss (one request per person). |
| `people_stats_win_loss_pitching` | `mlb_people_stats_win_loss_pitching` | `season` | 69 | `person_id`, `season`, `stat_games_played` | Per-player pitching stats, type winLoss (one request per person). |
| `people_stats_year_by_year_advanced_hitting` | `mlb_people_stats_year_by_year_advanced_hitting` | `season` | 51 | `person_id`, `player_id`, `sport_id`, `league_id`, `season`, `game_type`, `stat_plate_appearances` | Per-player hitting stats, type yearByYearAdvanced (one request per person). |
| `people_stats_year_by_year_advanced_pitching` | `mlb_people_stats_year_by_year_advanced_pitching` | `season` | 77 | `person_id`, `player_id`, `sport_id`, `league_id`, `season`, `game_type`, `stat_winning_percentage` | Per-player pitching stats, type yearByYearAdvanced (one request per person). |
| `people_stats_year_by_year_catching` | `mlb_people_stats_year_by_year_catching` | `season` | 48 | `person_id`, `player_id`, `team_id`, `sport_id`, `league_id`, `season` | Per-player catching stats, type yearByYear (one request per person). |
| `people_stats_year_by_year_fielding` | `mlb_people_stats_year_by_year_fielding` | `season` | 53 | `person_id`, `player_id`, `sport_id`, `league_id`, `season`, `game_type`, `position_abbreviation`, `stat_games_played` | Per-player fielding stats, type yearByYear (one request per person). |
| `people_stats_year_by_year_hitting` | `mlb_people_stats_year_by_year_hitting` | `season` | 54 | `person_id`, `player_id`, `sport_id`, `league_id`, `season`, `game_type`, `stat_games_played` | Per-player hitting stats, type yearByYear (one request per person). |
| `people_stats_year_by_year_pitching` | `mlb_people_stats_year_by_year_pitching` | `season` | 83 | `person_id`, `player_id`, `sport_id`, `league_id`, `season`, `game_type`, `stat_games_played` | Per-player pitching stats, type yearByYear (one request per person). |
| `people_stats_year_by_year_playoffs_catching` | `mlb_people_stats_year_by_year_playoffs_catching` | `season` | 48 | `person_id`, `player_id`, `team_id`, `sport_id`, `league_id`, `season` | Per-player catching stats, type yearByYearPlayoffs (one request per person). |
| `people_stats_year_by_year_playoffs_fielding` | `mlb_people_stats_year_by_year_playoffs_fielding` | `season` | 53 | `person_id`, `player_id`, `sport_id`, `league_id`, `game_type`, `position_abbreviation`, `stat_age`, `stat_games_played` | Per-player fielding stats, type yearByYearPlayoffs (one request per person). |
| `people_stats_year_by_year_playoffs_hitting` | `mlb_people_stats_year_by_year_playoffs_hitting` | `season` | 54 | `person_id`, `player_id`, `sport_id`, `league_id`, `game_type`, `stat_age`, `stat_games_played` | Per-player hitting stats, type yearByYearPlayoffs (one request per person). |
| `people_stats_year_by_year_playoffs_pitching` | `mlb_people_stats_year_by_year_playoffs_pitching` | `season` | 83 | `person_id`, `player_id`, `sport_id`, `league_id`, `game_type`, `stat_at_bats` | Per-player pitching stats, type yearByYearPlayoffs (one request per person). |
| `players_season` | `mlb_players_season` | `season` | 56 | `id`, `sport_id` | Every player of a sport-season with biographical fields. |
| `ref_awards` | `mlb_ref_awards` | `none` | 11 | `id` | Award catalog. |
| `ref_baseball_stats` | `mlb_ref_baseball_stats` | `none` | 9 | `name`, `stat_groups` | Statistic definitions (name, group, lookup param). |
| `ref_conferences` | `mlb_ref_conferences` | `none` | 11 | `id` | All conferences. |
| `ref_divisions` | `mlb_ref_divisions` | `none` | 15 | `id` | All divisions. |
| `ref_event_types` | `mlb_ref_event_types` | `none` | 6 | `code` | Play event types. |
| `ref_game_status` | `mlb_ref_game_status` | `none` | 7 | `status_code` | Game status codes. |
| `ref_game_types` | `mlb_ref_game_types` | `none` | 3 | `id` | Game type codes (R, P, S, ...). |
| `ref_hit_trajectories` | `mlb_ref_hit_trajectories` | `none` | 3 | `code` | Batted-ball trajectories. |
| `ref_job_types` | `mlb_ref_job_types` | `none` | 4 | `code` | Job (role) types. |
| `ref_languages` | `mlb_ref_languages` | `none` | 5 | `language_code` | Languages. |
| `ref_league` | `mlb_ref_league` | `none` | 41 | `id` | All leagues. |
| `ref_league_leader_types` | `mlb_ref_league_leader_types` | `none` | 2 | `display_name` | League leader categories. |
| `ref_logical_events` | `mlb_ref_logical_events` | `none` | 2 | `code` | Logical event types. |
| `ref_metrics` | `mlb_ref_metrics` | `none` | 5 | `metric_id` | Tracking metrics. |
| `ref_pitch_types` | `mlb_ref_pitch_types` | `none` | 3 | `code` | Pitch type codes. |
| `ref_platforms` | `mlb_ref_platforms` | `none` | 3 | `platform_code` | Platforms. |
| `ref_positions` | `mlb_ref_positions` | `none` | 12 | `abbrev` | Fielding/lineup positions. |
| `ref_review_reasons` | `mlb_ref_review_reasons` | `none` | 3 | `code` | Replay review reasons. |
| `ref_roster_types` | `mlb_ref_roster_types` | `none` | 4 | `parameter` | Roster types (active, 40Man, fullSeason, ...). |
| `ref_schedule_event_types` | `mlb_ref_schedule_event_types` | `none` | 3 | `code` | Schedule event types. |
| `ref_schedule_types` | `mlb_ref_schedule_types` | `none` | 3 | `id` | Schedule types. |
| `ref_situation_codes` | `mlb_ref_situation_codes` | `none` | 9 | `code` | Situation (split) codes. |
| `ref_sports` | `mlb_ref_sports` | `none` | 8 | `id` | Sports / levels (MLB, AAA, ...). |
| `ref_standings_types` | `mlb_ref_standings_types` | `none` | 3 | `name` | Standings types (regularSeason, wildCard, ...). |
| `ref_stat_groups` | `mlb_ref_stat_groups` | `none` | 2 | `display_name` | Stat groups (hitting, pitching, fielding, ...). |
| `ref_stat_types` | `mlb_ref_stat_types` | `none` | 2 | `display_name` | Stat type names usable in /v1/stats (season, career, gameLog, ...). |
| `ref_wind_direction` | `mlb_ref_wind_direction` | `none` | 3 | `code` | Wind direction codes. |
| `rosters` | `mlb_rosters` | `none` | 7 | `team_id`, `player_id` | Active team rosters. |
| `schedule` | `mlb_schedule` | `season` | 16 | `game_pk` | Game schedule. |
| `schedule_hydrated` | `mlb_schedule_hydrated` | `season` | 264 | `game_pk`, `dates_date`, `sport_id` | Season schedule with team, linescore, decisions, probable pitchers, officials, weather, venue, broadcasts, series and flags hydrated. |
| `schedule_postseason` | `mlb_schedule_postseason` | `season` | 66 | `game_pk` | Postseason games of a season. |
| `schedule_postseason_series` | `mlb_schedule_postseason_series` | `season` | 10 | `series_id` | Postseason series of a season. |
| `seasons_all` | `mlb_seasons_all` | `none` | 22 | `season_id` | Every season of a sport (calendar dates). |
| `standings` | `mlb_standings` | `season` | 13 | `season`, `team_id` | League and division standings. |
| `standings_by_conference` | `mlb_standings_by_conference` | `season` | 58 | `team_id`, `records_standings_type` | Standings, type byConference. |
| `standings_by_division` | `mlb_standings_by_division` | `season` | 58 | `team_id`, `records_standings_type` | Standings, type byDivision. |
| `standings_by_league` | `mlb_standings_by_league` | `season` | 58 | `team_id`, `records_standings_type` | Standings, type byLeague. |
| `standings_by_organization` | `mlb_standings_by_organization` | `season` | 78 | `team_id`, `records_standings_type` | Standings, type byOrganization. |
| `standings_current_half` | `mlb_standings_current_half` | `season` | 58 | `team_id`, `records_standings_type` | Standings, type currentHalf. |
| `standings_division_leaders` | `mlb_standings_division_leaders` | `season` | 56 | `team_id`, `records_standings_type` | Standings, type divisionLeaders. |
| `standings_first_half` | `mlb_standings_first_half` | `season` | 57 | `team_id`, `records_standings_type` | Standings, type firstHalf. |
| `standings_regular_season` | `mlb_standings_regular_season` | `season` | 58 | `team_id`, `records_standings_type` | Standings, type regularSeason. |
| `standings_second_half` | `mlb_standings_second_half` | `season` | 57 | `team_id`, `records_standings_type` | Standings, type secondHalf. |
| `standings_spring_training` | `mlb_standings_spring_training` | `season` | 77 | `team_id`, `records_standings_type` | Standings, type springTraining. |
| `standings_wild_card` | `mlb_standings_wild_card` | `season` | 54 | `team_id`, `records_standings_type` | Standings, type wildCard. |
| `standings_wild_card_with_leaders` | `mlb_standings_wild_card_with_leaders` | `season` | 58 | `team_id`, `records_standings_type` | Standings, type wildCardWithLeaders. |
| `stats_career_advanced_catching` | `mlb_stats_career_advanced_catching` | `season` | 66 | `player_id` | League-wide catching stats, type careerAdvanced (player pool ALL). |
| `stats_career_advanced_fielding` | `mlb_stats_career_advanced_fielding` | `season` | 55 | `player_id`, `team_id`, `sport_id`, `position_abbreviation` | League-wide fielding stats, type careerAdvanced (player pool ALL). |
| `stats_career_advanced_hitting` | `mlb_stats_career_advanced_hitting` | `season` | 58 | `player_id` | League-wide hitting stats, type careerAdvanced (player pool ALL). |
| `stats_career_advanced_pitching` | `mlb_stats_career_advanced_pitching` | `season` | 83 | `player_id` | League-wide pitching stats, type careerAdvanced (player pool ALL). |
| `stats_career_catching` | `mlb_stats_career_catching` | `season` | 66 | `player_id` | League-wide catching stats, type career (player pool ALL). |
| `stats_career_fielding` | `mlb_stats_career_fielding` | `season` | 55 | `player_id`, `team_id`, `sport_id`, `position_abbreviation` | League-wide fielding stats, type career (player pool ALL). |
| `stats_career_hitting` | `mlb_stats_career_hitting` | `season` | 61 | `player_id` | League-wide hitting stats, type career (player pool ALL). |
| `stats_career_pitching` | `mlb_stats_career_pitching` | `season` | 89 | `player_id` | League-wide pitching stats, type career (player pool ALL). |
| `stats_career_stat_splits_fielding` | `mlb_stats_career_stat_splits_fielding` | `season` | 19 | `player_id`, `split_code` | League-wide fielding stats, type careerStatSplits, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'} (player pool ALL). |
| `stats_career_stat_splits_hitting` | `mlb_stats_career_stat_splits_hitting` | `season` | 62 | `player_id`, `split_code` | League-wide hitting stats, type careerStatSplits, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'} (player pool ALL). |
| `stats_career_stat_splits_pitching` | `mlb_stats_career_stat_splits_pitching` | `season` | 91 | `player_id`, `split_code` | League-wide pitching stats, type careerStatSplits, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'} (player pool ALL). |
| `stats_expected_statistics_hitting` | `mlb_stats_expected_statistics_hitting` | `season` | 29 | `player_id` | League-wide hitting stats, type expectedStatistics (player pool ALL). |
| `stats_expected_statistics_pitching` | `mlb_stats_expected_statistics_pitching` | `season` | 25 | `player_id`, `sport_id` | League-wide pitching stats, type expectedStatistics (player pool ALL). |
| `stats_last_x_games_fielding` | `mlb_stats_last_x_games_fielding` | `season` | 57 | `player_id` | League-wide fielding stats, type lastXGames (player pool ALL). |
| `stats_last_x_games_hitting` | `mlb_stats_last_x_games_hitting` | `season` | 65 | `player_id` | League-wide hitting stats, type lastXGames (player pool ALL). |
| `stats_last_x_games_pitching` | `mlb_stats_last_x_games_pitching` | `season` | 92 | `player_id` | League-wide pitching stats, type lastXGames (player pool ALL). |
| `stats_leaders` | `mlb_stats_leaders` | `season` | 26 | `sport_id`, `league_leaders_season`, `league_leaders_game_type_id`, `league_leaders_leader_category`, `league_leaders_stat_group`, `rank`, `person_id` | League leaders for every category of a season-sport (ties repeat a rank; the person completes the key, a few provider rows are repeated). |
| `stats_outs_above_average_catching` | `mlb_stats_outs_above_average_catching` | `season` | 39 | `player_id` | League-wide catching stats, type outsAboveAverage (player pool ALL). |
| `stats_outs_above_average_fielding` | `mlb_stats_outs_above_average_fielding` | `season` | 39 | `player_id` | League-wide fielding stats, type outsAboveAverage (player pool ALL). |
| `stats_outs_above_average_game` | `mlb_stats_outs_above_average_game` | `season` | 39 | `player_id` | League-wide game stats, type outsAboveAverage (player pool ALL). |
| `stats_outs_above_average_hitting` | `mlb_stats_outs_above_average_hitting` | `season` | 39 | `player_id` | League-wide hitting stats, type outsAboveAverage (player pool ALL). |
| `stats_outs_above_average_pitching` | `mlb_stats_outs_above_average_pitching` | `season` | 39 | `player_id` | League-wide pitching stats, type outsAboveAverage (player pool ALL). |
| `stats_outs_above_average_running` | `mlb_stats_outs_above_average_running` | `season` | 39 | `player_id` | League-wide running stats, type outsAboveAverage (player pool ALL). |
| `stats_outs_above_average_streak` | `mlb_stats_outs_above_average_streak` | `season` | 39 | `player_id` | League-wide streak stats, type outsAboveAverage (player pool ALL). |
| `stats_outs_above_average_team` | `mlb_stats_outs_above_average_team` | `season` | 39 | `player_id` | League-wide team stats, type outsAboveAverage (player pool ALL). |
| `stats_projected_hitting` | `mlb_stats_projected_hitting` | `season` | 66 | `player_id` | League-wide hitting stats, type projected (player pool ALL). |
| `stats_projected_pitching` | `mlb_stats_projected_pitching` | `season` | 65 | `player_id` | League-wide pitching stats, type projected (player pool ALL). |
| `stats_projected_zips2_yr_hitting` | `mlb_stats_projected_zips2_yr_hitting` | `season` | 70 | `player_id` | League-wide hitting stats, type projected_Zips2YR, parameters {} (player pool ALL). |
| `stats_projected_zips2_yr_pitching` | `mlb_stats_projected_zips2_yr_pitching` | `season` | 69 | `player_id` | League-wide pitching stats, type projected_Zips2YR, parameters {} (player pool ALL). |
| `stats_projected_zips3_yr_hitting` | `mlb_stats_projected_zips3_yr_hitting` | `season` | 70 | `player_id` | League-wide hitting stats, type projected_Zips3YR, parameters {} (player pool ALL). |
| `stats_projected_zips3_yr_pitching` | `mlb_stats_projected_zips3_yr_pitching` | `season` | 69 | `player_id` | League-wide pitching stats, type projected_Zips3YR, parameters {} (player pool ALL). |
| `stats_projected_zips_hitting` | `mlb_stats_projected_zips_hitting` | `season` | 70 | `player_id` | League-wide hitting stats, type projected_Zips, parameters {} (player pool ALL). |
| `stats_projected_zips_pitching` | `mlb_stats_projected_zips_pitching` | `season` | 69 | `player_id` | League-wide pitching stats, type projected_Zips, parameters {} (player pool ALL). |
| `stats_sabermetrics_fielding` | `mlb_stats_sabermetrics_fielding` | `season` | 35 | `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `position_abbreviation` | League-wide fielding stats, type sabermetrics (player pool ALL). |
| `stats_sabermetrics_hitting` | `mlb_stats_sabermetrics_hitting` | `season` | 46 | `player_id` | League-wide hitting stats, type sabermetrics (player pool ALL). |
| `stats_sabermetrics_pitching` | `mlb_stats_sabermetrics_pitching` | `season` | 43 | `player_id` | League-wide pitching stats, type sabermetrics (player pool ALL). |
| `stats_season_advanced_catching` | `mlb_stats_season_advanced_catching` | `season` | 70 | `player_id` | League-wide catching stats, type seasonAdvanced (player pool ALL). |
| `stats_season_advanced_fielding` | `mlb_stats_season_advanced_fielding` | `season` | 54 | `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `position_abbreviation` | League-wide fielding stats, type seasonAdvanced (player pool ALL). |
| `stats_season_advanced_game` | `mlb_stats_season_advanced_game` | `season` | 28 | `player_id` | League-wide game stats, type seasonAdvanced (player pool ALL). |
| `stats_season_advanced_hitting` | `mlb_stats_season_advanced_hitting` | `season` | 61 | `player_id` | League-wide hitting stats, type seasonAdvanced (player pool ALL). |
| `stats_season_advanced_pitching` | `mlb_stats_season_advanced_pitching` | `season` | 86 | `player_id` | League-wide pitching stats, type seasonAdvanced (player pool ALL). |
| `stats_season_catching` | `mlb_stats_season_catching` | `season` | 70 | `player_id` | League-wide catching stats, type season (player pool ALL). |
| `stats_season_fielding` | `mlb_stats_season_fielding` | `season` | 54 | `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `position_abbreviation` | League-wide fielding stats, type season (player pool ALL). |
| `stats_season_game` | `mlb_stats_season_game` | `season` | 28 | `player_id` | League-wide game stats, type season (player pool ALL). |
| `stats_season_hitting` | `mlb_stats_season_hitting` | `season` | 64 | `player_id` | League-wide hitting stats, type season (player pool ALL). |
| `stats_season_pitching` | `mlb_stats_season_pitching` | `season` | 92 | `player_id` | League-wide pitching stats, type season (player pool ALL). |
| `stats_stat_splits_advanced_catching` | `mlb_stats_stat_splits_advanced_catching` | `season` | 31 | `season` | League-wide catching stats, type statSplitsAdvanced, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'} (player pool ALL). |
| `stats_stat_splits_advanced_fielding` | `mlb_stats_stat_splits_advanced_fielding` | `season` | 28 | `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `split_code` | League-wide fielding stats, type statSplitsAdvanced, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'} (player pool ALL). |
| `stats_stat_splits_advanced_hitting` | `mlb_stats_stat_splits_advanced_hitting` | `season` | 50 | `season` | League-wide hitting stats, type statSplitsAdvanced, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'} (player pool ALL). |
| `stats_stat_splits_advanced_pitching` | `mlb_stats_stat_splits_advanced_pitching` | `season` | 63 | `season` | League-wide pitching stats, type statSplitsAdvanced, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'} (player pool ALL). |
| `stats_stat_splits_advanced_running` | `mlb_stats_stat_splits_advanced_running` | `season` | 31 | `season` | League-wide running stats, type statSplitsAdvanced, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'} (player pool ALL). |
| `stats_stat_splits_catching` | `mlb_stats_stat_splits_catching` | `season` | 31 | `season` | League-wide catching stats, type statSplits, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'} (player pool ALL). |
| `stats_stat_splits_fielding` | `mlb_stats_stat_splits_fielding` | `season` | 28 | `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `split_code` | League-wide fielding stats, type statSplits, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'} (player pool ALL). |
| `stats_stat_splits_hitting` | `mlb_stats_stat_splits_hitting` | `season` | 65 | `season` | League-wide hitting stats, type statSplits, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'} (player pool ALL). |
| `stats_stat_splits_pitching` | `mlb_stats_stat_splits_pitching` | `season` | 94 | `season` | League-wide pitching stats, type statSplits, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'} (player pool ALL). |
| `stats_stat_splits_running` | `mlb_stats_stat_splits_running` | `season` | 31 | `season` | League-wide running stats, type statSplits, parameters {'season': '{season}', 'sitCodes': '{sit_codes}'} (player pool ALL). |
| `stats_stats_single_season_advanced_catching` | `mlb_stats_stats_single_season_advanced_catching` | `season` | 67 | `player_id`, `team_id`, `sport_id`, `league_id`, `season` | League-wide catching stats, type statsSingleSeasonAdvanced (player pool ALL). |
| `stats_stats_single_season_advanced_fielding` | `mlb_stats_stats_single_season_advanced_fielding` | `season` | 45 | `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `position_abbreviation` | League-wide fielding stats, type statsSingleSeasonAdvanced (player pool ALL). |
| `stats_stats_single_season_advanced_hitting` | `mlb_stats_stats_single_season_advanced_hitting` | `season` | 60 | `player_id`, `team_id`, `sport_id`, `league_id`, `season` | League-wide hitting stats, type statsSingleSeasonAdvanced (player pool ALL). |
| `stats_stats_single_season_advanced_pitching` | `mlb_stats_stats_single_season_advanced_pitching` | `season` | 85 | `player_id`, `team_id`, `sport_id`, `league_id`, `season` | League-wide pitching stats, type statsSingleSeasonAdvanced (player pool ALL). |
| `stats_stats_single_season_catching` | `mlb_stats_stats_single_season_catching` | `season` | 67 | `player_id`, `team_id`, `sport_id`, `league_id`, `season` | League-wide catching stats, type statsSingleSeason (player pool ALL). |
| `stats_stats_single_season_fielding` | `mlb_stats_stats_single_season_fielding` | `season` | 45 | `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `position_abbreviation` | League-wide fielding stats, type statsSingleSeason (player pool ALL). |
| `stats_stats_single_season_hitting` | `mlb_stats_stats_single_season_hitting` | `season` | 63 | `player_id`, `team_id`, `sport_id`, `league_id`, `season` | League-wide hitting stats, type statsSingleSeason (player pool ALL). |
| `stats_stats_single_season_pitching` | `mlb_stats_stats_single_season_pitching` | `season` | 91 | `player_id`, `team_id`, `sport_id`, `league_id`, `season` | League-wide pitching stats, type statsSingleSeason (player pool ALL). |
| `team_affiliates` | `mlb_team_affiliates` | `season` | 37 | `id`, `parent_org_id` | Minor-league affiliates of every MLB club. |
| `team_alumni` | `mlb_team_alumni` | `season` | 54 | `team_id`, `id` | Club alumni (hitting) of a season. |
| `team_coaches` | `mlb_team_coaches` | `season` | 9 | `team_id`, `person_id`, `job` | Coaching staff of a club-season. A coach who changed jersey number appears twice (an empty jersey number is NULL, so it cannot be a key part): the key is not unique. |
| `team_history` | `mlb_team_history` | `none` | 27 | `id`, `season` | Franchise history (names/locations by season). |
| `team_personnel` | `mlb_team_personnel` | `season` | 9 | `team_id`, `person_id`, `job` | Non-playing personnel of a club-season. The provider repeats a row for one person: the key is not unique. |
| `team_roster_40_man` | `mlb_team_roster_40_man` | `season` | 12 | `team_id`, `person_id`, `position_code` | Team roster, type 40Man. |
| `team_roster_active` | `mlb_team_roster_active` | `season` | 12 | `team_id`, `person_id`, `position_code` | Team roster, type active. |
| `team_roster_all_time` | `mlb_team_roster_all_time` | `season` | 14 | `team_id`, `person_id`, `position_code` | Team roster, type allTime. |
| `team_roster_coach` | `mlb_team_roster_coach` | `season` | 9 | `team_id`, `person_id`, `job` | Team roster, type coach. |
| `team_roster_depth_chart` | `mlb_team_roster_depth_chart` | `season` | 12 | `team_id`, `person_id`, `position_code` | Team roster, type depthChart. |
| `team_roster_full_roster` | `mlb_team_roster_full_roster` | `season` | 12 | `team_id`, `person_id`, `position_code` | Team roster, type fullRoster. |
| `team_roster_full_season` | `mlb_team_roster_full_season` | `season` | 12 | `team_id`, `person_id`, `position_code` | Team roster, type fullSeason. |
| `team_roster_gameday` | `mlb_team_roster_gameday` | `season` | 13 | `team_id`, `person_id`, `position_code` | Team roster, type gameday. |
| `team_roster_non_roster_invitees` | `mlb_team_roster_non_roster_invitees` | `season` | 12 | `team_id`, `person_id`, `position_code` | Team roster, type nonRosterInvitees. |
| `team_stats_at_game_start_catching` | `mlb_team_stats_at_game_start_catching` | `season` | 49 | `team_id`, `season`, `date`, `opponent_id`, `game_game_pk` | Team catching stats, type atGameStart. |
| `team_stats_at_game_start_fielding` | `mlb_team_stats_at_game_start_fielding` | `season` | 37 | `team_id`, `season`, `date`, `game_game_pk` | Team fielding stats, type atGameStart. |
| `team_stats_at_game_start_hitting` | `mlb_team_stats_at_game_start_hitting` | `season` | 55 | `team_id`, `season`, `date`, `game_game_pk` | Team hitting stats, type atGameStart. |
| `team_stats_at_game_start_pitching` | `mlb_team_stats_at_game_start_pitching` | `season` | 82 | `team_id`, `season`, `date`, `game_game_pk` | Team pitching stats, type atGameStart. |
| `team_stats_by_date_range_catching` | `mlb_team_stats_by_date_range_catching` | `season` | 39 | `team_id` | Team catching stats, type byDateRange. |
| `team_stats_by_date_range_fielding` | `mlb_team_stats_by_date_range_fielding` | `season` | 27 | `team_id` | Team fielding stats, type byDateRange. |
| `team_stats_by_date_range_hitting` | `mlb_team_stats_by_date_range_hitting` | `season` | 45 | `team_id` | Team hitting stats, type byDateRange. |
| `team_stats_by_date_range_pitching` | `mlb_team_stats_by_date_range_pitching` | `season` | 72 | `team_id` | Team pitching stats, type byDateRange. |
| `team_stats_career_advanced_catching` | `mlb_team_stats_career_advanced_catching` | `season` | 40 | `team_id` | Team catching stats, type careerAdvanced. |
| `team_stats_career_advanced_fielding` | `mlb_team_stats_career_advanced_fielding` | `season` | 25 | `team_id` | Team fielding stats, type careerAdvanced. |
| `team_stats_career_advanced_hitting` | `mlb_team_stats_career_advanced_hitting` | `season` | 41 | `team_id` | Team hitting stats, type careerAdvanced. |
| `team_stats_career_advanced_pitching` | `mlb_team_stats_career_advanced_pitching` | `season` | 62 | `team_id` | Team pitching stats, type careerAdvanced. |
| `team_stats_career_catching` | `mlb_team_stats_career_catching` | `season` | 40 | `team_id` | Team catching stats, type career. |
| `team_stats_career_fielding` | `mlb_team_stats_career_fielding` | `season` | 25 | `team_id` | Team fielding stats, type career. |
| `team_stats_career_hitting` | `mlb_team_stats_career_hitting` | `season` | 44 | `team_id` | Team hitting stats, type career. |
| `team_stats_career_pitching` | `mlb_team_stats_career_pitching` | `season` | 70 | `team_id` | Team pitching stats, type career. |
| `team_stats_career_playoffs_catching` | `mlb_team_stats_career_playoffs_catching` | `season` | 40 | `team_id`, `season` | Team catching stats, type careerPlayoffs. |
| `team_stats_career_playoffs_fielding` | `mlb_team_stats_career_playoffs_fielding` | `season` | 26 | `team_id`, `season` | Team fielding stats, type careerPlayoffs. |
| `team_stats_career_playoffs_hitting` | `mlb_team_stats_career_playoffs_hitting` | `season` | 38 | `team_id`, `season` | Team hitting stats, type careerPlayoffs. |
| `team_stats_career_playoffs_pitching` | `mlb_team_stats_career_playoffs_pitching` | `season` | 47 | `team_id`, `season` | Team pitching stats, type careerPlayoffs. |
| `team_stats_career_regular_season_catching` | `mlb_team_stats_career_regular_season_catching` | `season` | 40 | `team_id`, `season` | Team catching stats, type careerRegularSeason. |
| `team_stats_career_regular_season_fielding` | `mlb_team_stats_career_regular_season_fielding` | `season` | 26 | `team_id`, `season` | Team fielding stats, type careerRegularSeason. |
| `team_stats_career_regular_season_hitting` | `mlb_team_stats_career_regular_season_hitting` | `season` | 38 | `team_id`, `season` | Team hitting stats, type careerRegularSeason. |
| `team_stats_career_regular_season_pitching` | `mlb_team_stats_career_regular_season_pitching` | `season` | 47 | `team_id`, `season` | Team pitching stats, type careerRegularSeason. |
| `team_stats_game_log_catching` | `mlb_team_stats_game_log_catching` | `season` | 49 | `team_id`, `season`, `date`, `opponent_id`, `game_game_pk` | Team catching stats, type gameLog. |
| `team_stats_game_log_fielding` | `mlb_team_stats_game_log_fielding` | `season` | 37 | `team_id`, `season`, `date`, `game_game_pk` | Team fielding stats, type gameLog. |
| `team_stats_game_log_hitting` | `mlb_team_stats_game_log_hitting` | `season` | 55 | `team_id`, `season`, `date`, `game_game_pk` | Team hitting stats, type gameLog. |
| `team_stats_game_log_pitching` | `mlb_team_stats_game_log_pitching` | `season` | 82 | `team_id`, `season`, `date`, `game_game_pk` | Team pitching stats, type gameLog. |
| `team_stats_last_x_games_catching` | `mlb_team_stats_last_x_games_catching` | `season` | 39 | `team_id` | Team catching stats, type lastXGames. |
| `team_stats_last_x_games_fielding` | `mlb_team_stats_last_x_games_fielding` | `season` | 27 | `team_id` | Team fielding stats, type lastXGames. |
| `team_stats_last_x_games_hitting` | `mlb_team_stats_last_x_games_hitting` | `season` | 45 | `team_id` | Team hitting stats, type lastXGames. |
| `team_stats_last_x_games_pitching` | `mlb_team_stats_last_x_games_pitching` | `season` | 72 | `team_id` | Team pitching stats, type lastXGames. |
| `team_stats_season_advanced_catching` | `mlb_team_stats_season_advanced_catching` | `season` | 43 | `team_id` | Team catching stats, type seasonAdvanced. |
| `team_stats_season_advanced_fielding` | `mlb_team_stats_season_advanced_fielding` | `season` | 35 | `team_id` | Team fielding stats, type seasonAdvanced. |
| `team_stats_season_advanced_hitting` | `mlb_team_stats_season_advanced_hitting` | `season` | 43 | `team_id` | Team hitting stats, type seasonAdvanced. |
| `team_stats_season_advanced_pitching` | `mlb_team_stats_season_advanced_pitching` | `season` | 64 | `team_id` | Team pitching stats, type seasonAdvanced. |
| `team_stats_season_catching` | `mlb_team_stats_season_catching` | `season` | 43 | `team_id` | Team catching stats, type season. |
| `team_stats_season_fielding` | `mlb_team_stats_season_fielding` | `season` | 35 | `team_id` | Team fielding stats, type season. |
| `team_stats_season_hitting` | `mlb_team_stats_season_hitting` | `season` | 46 | `team_id` | Team hitting stats, type season. |
| `team_stats_season_pitching` | `mlb_team_stats_season_pitching` | `season` | 72 | `team_id` | Team pitching stats, type season. |
| `team_stats_vs_opponents_fielding` | `mlb_team_stats_vs_opponents_fielding` | `season` | 30 | `team_id` | Team fielding stats, type vsOpponents. |
| `team_stats_vs_opponents_hitting` | `mlb_team_stats_vs_opponents_hitting` | `season` | 51 | `team_id` | Team hitting stats, type vsOpponents. |
| `team_stats_vs_opponents_pitching` | `mlb_team_stats_vs_opponents_pitching` | `season` | 80 | `team_id` | Team pitching stats, type vsOpponents. |
| `team_stats_year_by_year_advanced_catching` | `mlb_team_stats_year_by_year_advanced_catching` | `season` | 40 | `team_id`, `season` | Team catching stats, type yearByYearAdvanced. |
| `team_stats_year_by_year_advanced_fielding` | `mlb_team_stats_year_by_year_advanced_fielding` | `season` | 26 | `team_id`, `season` | Team fielding stats, type yearByYearAdvanced. |
| `team_stats_year_by_year_advanced_hitting` | `mlb_team_stats_year_by_year_advanced_hitting` | `season` | 42 | `team_id`, `season` | Team hitting stats, type yearByYearAdvanced. |
| `team_stats_year_by_year_advanced_pitching` | `mlb_team_stats_year_by_year_advanced_pitching` | `season` | 63 | `team_id`, `season` | Team pitching stats, type yearByYearAdvanced. |
| `team_stats_year_by_year_catching` | `mlb_team_stats_year_by_year_catching` | `season` | 40 | `team_id`, `season` | Team catching stats, type yearByYear. |
| `team_stats_year_by_year_fielding` | `mlb_team_stats_year_by_year_fielding` | `season` | 26 | `team_id`, `season` | Team fielding stats, type yearByYear. |
| `team_stats_year_by_year_hitting` | `mlb_team_stats_year_by_year_hitting` | `season` | 45 | `team_id`, `season` | Team hitting stats, type yearByYear. |
| `team_stats_year_by_year_pitching` | `mlb_team_stats_year_by_year_pitching` | `season` | 71 | `team_id`, `season` | Team pitching stats, type yearByYear. |
| `team_stats_year_by_year_playoffs_catching` | `mlb_team_stats_year_by_year_playoffs_catching` | `season` | 40 | `team_id`, `season` | Team catching stats, type yearByYearPlayoffs. |
| `team_stats_year_by_year_playoffs_fielding` | `mlb_team_stats_year_by_year_playoffs_fielding` | `season` | 26 | `team_id`, `season` | Team fielding stats, type yearByYearPlayoffs. |
| `team_stats_year_by_year_playoffs_hitting` | `mlb_team_stats_year_by_year_playoffs_hitting` | `season` | 38 | `team_id`, `season` | Team hitting stats, type yearByYearPlayoffs. |
| `team_stats_year_by_year_playoffs_pitching` | `mlb_team_stats_year_by_year_playoffs_pitching` | `season` | 47 | `team_id`, `season` | Team pitching stats, type yearByYearPlayoffs. |
| `teams` | `mlb_teams` | `none` | 10 | `team_id` | MLB franchises. |
| `teams_season` | `mlb_teams_season` | `season` | 40 | `id` | Teams of a season (sport 1 = MLB). |
| `transactions` | `mlb_transactions` | `season` | 9 | `transaction_id` | Roster transactions. |
| `transactions_season` | `mlb_transactions_season` | `season` | 17 | `id` | Every transaction of a calendar year (trades, signings, DFAs, IL moves, ...), all fields. A trade has one id for several people and person_id can be empty, so the key is not unique: export with replace or append. |
| `venues` | `mlb_venues` | `none` | 8 | `venue_id` | Official ballparks. |
| `venues_hydrated` | `mlb_venues_hydrated` | `none` | 34 | `id` | Every venue with location, field info, time zone and external ids hydrated. |

### LAHMAN (27 datasets)

| Dataset Name | View Name | Partition | Columns | Primary Keys | Description |
| :--- | :--- | :--- | :---: | :--- | :--- |
| `AllstarFull` | `lahman_allstarfull` | `none` | 9 | `playerID`, `yearID`, `gameNum`, `gameID`, `teamID`, `lgID` | Lahman AllstarFull table. |
| `Appearances` | `lahman_appearances` | `none` | 22 | `yearID`, `teamID`, `playerID` | Lahman Appearances table. |
| `AwardsManagers` | `lahman_awardsmanagers` | `none` | 7 | `playerID`, `awardID`, `yearID`, `lgID` | Lahman AwardsManagers table. |
| `AwardsPlayers` | `lahman_awardsplayers` | `none` | 7 | `playerID`, `awardID`, `yearID`, `lgID`, `notes` | Lahman AwardsPlayers table. |
| `AwardsShareManagers` | `lahman_awardssharemanagers` | `none` | 8 | `awardID`, `yearID`, `lgID`, `playerID` | Lahman AwardsShareManagers table. |
| `AwardsSharePlayers` | `lahman_awardsshareplayers` | `none` | 8 | `awardID`, `yearID`, `lgID`, `playerID` | Lahman AwardsSharePlayers table. |
| `Batting` | `lahman_batting` | `none` | 23 | `playerID`, `yearID`, `stint` | Lahman Batting table. |
| `BattingPost` | `lahman_battingpost` | `none` | 23 | `yearID`, `round`, `playerID` | Lahman BattingPost table. |
| `CollegePlaying` | `lahman_collegeplaying` | `none` | 4 | `playerID`, `schoolID`, `yearID` | Lahman CollegePlaying table. |
| `Fielding` | `lahman_fielding` | `none` | 19 | `playerID`, `yearID`, `stint`, `POS` | Lahman Fielding table. |
| `FieldingOF` | `lahman_fieldingof` | `none` | 7 | `playerID`, `yearID`, `stint` | Lahman FieldingOF table. |
| `FieldingOFsplit` | `lahman_fieldingofsplit` | `none` | 19 | `playerID`, `yearID`, `stint`, `POS` | Lahman FieldingOFsplit table. |
| `FieldingPost` | `lahman_fieldingpost` | `none` | 18 | `playerID`, `yearID`, `round`, `POS` | Lahman FieldingPost table. |
| `HallOfFame` | `lahman_halloffame` | `none` | 10 | `playerID`, `yearid`, `votedBy` | Lahman HallOfFame table. |
| `HomeGames` | `lahman_homegames` | `none` | 10 | `yearkey`, `leaguekey`, `teamkey`, `parkkey` | Lahman HomeGames table. |
| `Managers` | `lahman_managers` | `none` | 11 | `yearID`, `teamID`, `inseason` | Lahman Managers table. |
| `ManagersHalf` | `lahman_managershalf` | `none` | 11 | `yearID`, `teamID`, `half`, `playerID` | Lahman ManagersHalf table. |
| `Parks` | `lahman_parks` | `none` | 8 | `parkkey` | Lahman Parks table. |
| `People` | `lahman_people` | `none` | 26 | `playerID` | Lahman People table. |
| `Pitching` | `lahman_pitching` | `none` | 31 | `playerID`, `yearID`, `stint` | Lahman Pitching table. |
| `PitchingPost` | `lahman_pitchingpost` | `none` | 31 | `yearID`, `round`, `playerID` | Lahman PitchingPost table. |
| `Salaries` | `lahman_salaries` | `none` | 6 | `yearID`, `teamID`, `lgID`, `playerID` | Lahman Salaries table. |
| `Schools` | `lahman_schools` | `none` | 6 | `schoolID` | Lahman Schools table. |
| `SeriesPost` | `lahman_seriespost` | `none` | 10 | `yearID`, `round` | Lahman SeriesPost table. |
| `Teams` | `lahman_teams` | `none` | 49 | `yearID`, `lgID`, `teamID` | Lahman Teams table. |
| `TeamsFranchises` | `lahman_teamsfranchises` | `none` | 5 | `franchID` | Lahman TeamsFranchises table. |
| `TeamsHalf` | `lahman_teamshalf` | `none` | 11 | `yearID`, `lgID`, `teamID`, `Half` | Lahman TeamsHalf table. |

### CHADWICK (4 datasets)

| Dataset Name | View Name | Partition | Columns | Primary Keys | Description |
| :--- | :--- | :--- | :---: | :--- | :--- |
| `register` | `chadwick_register` | `none` | 41 | `key_person` | Master player-ID crosswalk (data/people-*.csv shards). |
| `register_countries` | `chadwick_register_countries` | `none` | 6 | `key_iso_alpha2` | ISO / IOC / FIFA country codes (data/countries.csv). |
| `register_links` | `chadwick_register_links` | `none` | 4 | `key_person`, `source`, `value` | External player identifiers by source (data/links.csv). |
| `register_names` | `chadwick_register_names` | `none` | 17 | `key_person`, `altname_type`, `altname_lang`, `altname_last`, `altname_first`, `altname_given`, `altname_nick`, `altname_matrilineal`, `altname_date_start`, `altname_date_end` | Alternate names, spellings and nicknames (data/names.csv). |

### RETROSHEET (25 datasets)

| Dataset Name | View Name | Partition | Columns | Primary Keys | Description |
| :--- | :--- | :--- | :---: | :--- | :--- |
| `box_batting_lines` | `retrosheet_box_batting_lines` | `season` | 22 | `game_id`, `player_id`, `side`, `seq` | Batting and base-running lines of the box-score accounts (stat,bline). |
| `box_games` | `retrosheet_box_games` | `season` | 34 | `game_id` | Games of the box-score accounts (id, version, info lines). |
| `box_records` | `retrosheet_box_records` | `season` | 5 | `game_id`, `line_no` | Every other box-account record (pinch hitters/runners, fielding, pitching, team totals, line scores, events, comments, unknown kinds) as parsed fields plus the raw line. |
| `box_starters` | `retrosheet_box_starters` | `season` | 6 | `game_id`, `player_id`, `side`, `position` | Starting lineups of the box-score accounts (start lines). |
| `boxscores_batting` | `retrosheet_boxscores_batting` | `season` | 24 | `game_id`, `team_id`, `slot`, `seq` | Batting box score lines. |
| `boxscores_pitching` | `retrosheet_boxscores_pitching` | `season` | 26 | `game_id`, `team_id`, `pitcher_id`, `seq` | Pitching box score lines. |
| `daily_splits` | `retrosheet_daily_splits` | `season` | 154 | `GAME_ID`, `TEAM_ID`, `PLAYER_ID`, `SLOT_CT`, `SEQ_CT` | Daily player appearance lines. |
| `discrepancies` | `retrosheet_discrepancies` | `season` | 16 | `disc_id` | Known data discrepancies (seasons/<year>/*discs.csv). |
| `events` | `retrosheet_events` | `season` | 165 | `GAME_ID`, `EVENT_ID` | Regular-season play-by-play events. |
| `events_deduced` | `retrosheet_events_deduced` | `season` | 165 | `GAME_ID`, `EVENT_ID` | Play-by-play events deduced from box scores (.ED* files). |
| `events_postseason` | `retrosheet_events_postseason` | `season` | 165 | `GAME_ID`, `EVENT_ID` | Postseason and all-star play-by-play events. |
| `gamelogs` | `retrosheet_gamelogs` | `season` | 162 | `date`, `game_num`, `home_team` | Regular-season game logs. |
| `gamelogs_postseason` | `retrosheet_gamelogs_postseason` | `none` | 162 | `date`, `game_num`, `home_team` | Postseason and all-star game logs. |
| `reference_ballparks` | `retrosheet_reference_ballparks` | `none` | 10 | `park_id` | Ballparks (reference/ballparks.csv). |
| `reference_biofile` | `retrosheet_reference_biofile` | `none` | 34 | `player_id` | Biographical file (reference/biofile.csv). |
| `reference_biofile0` | `retrosheet_reference_biofile0` | `none` | 33 | `player_id` | Biographical file, ISO-date edition (reference/biofile0.csv). |
| `reference_coaches` | `retrosheet_reference_coaches` | `none` | 7 | `person_id`, `year`, `team_id`, `role`, `start_date` | Coaching staffs (reference/coaches.csv). |
| `reference_ejections` | `retrosheet_reference_ejections` | `none` | 12 | `game_id`, `ejectee_id`, `inning`, `reason` | Ejections (reference/ejections.csv). |
| `reference_relatives` | `retrosheet_reference_relatives` | `none` | 4 | `person_id_1`, `relation`, `person_id_2` | Relatives among players/managers (reference/relatives.csv). |
| `reference_teams` | `retrosheet_reference_teams` | `none` | 7 | `team_id`, `first_year` | Franchise/team codes (reference/teams.csv). |
| `rosters` | `retrosheet_rosters` | `season` | 10 | `year`, `roster`, `player_id` | Team rosters per season. |
| `schedule` | `retrosheet_schedule` | `season` | 14 | `game_date`, `game_number`, `visitor_team`, `visitor_game_number`, `home_team` | Season schedules (seasons/<year>/<year>schedule.csv). |
| `schedule_original` | `retrosheet_schedule_original` | `season` | 13 | `game_date`, `game_number`, `visitor_team`, `visitor_game_number`, `home_team` | Original pre-disruption schedules (seasons/<year>/<year>sched-orig.csv). |
| `substitutions` | `retrosheet_substitutions` | `season` | 26 | `GAME_ID`, `EVENT_ID`, `SUB_ID`, `SUB_FLD_CD` | In-game substitutions. |
| `umpires` | `retrosheet_umpires` | `season` | 4 | `umpire_id` | Umpires working each season (seasons/<year>/UMPIRES<year>.txt). |
