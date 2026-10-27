# Endpoint & Dataset Catalog (target coverage)

This is the authoritative list of what `baseballpy` must be able to download, normalize, store and document
(see `openspec/changes/complete-source-coverage`). It is a **target**, written from knowledge of the upstream
services as of 2026-10; every row must be **probed live** by `scripts/probe_endpoints.py`, and the
`Status` / `Verified on` columns updated from `docs/endpoint_probe.json`. Rows that do not respond are kept
and marked `unsupported` with the evidence (HTTP status + date) — never silently deleted.

Legend — **Partition**: `season` = Hive `season=YYYY`; `flat` = single `data.parquet`. **Keys**: natural key used for upserts and duplicate tests. **Fan-out**: how jobs are generated. Status values: `todo`, `implemented`, `verified`, `unsupported`.

Global rules for every dataset: all upstream fields are kept (typed columns + `_extras`); raw payload stored under `raw/`; freshness per policy; quarantine on bad rows; one audit event per job; view `<source>_<dataset>` in DuckDB; doc section generated from the spec.

---

## 1. MLB Stats API — `https://statsapi.mlb.com/api` (8 req/s, HTTP/2)

### 1.1 Reference / meta (flat, refresh 24 h) — dataset `mlb_ref_<name>`
`GET /v1/{name}` for: `gameTypes`, `statTypes`, `statGroups`, `leagueLeaderTypes`, `positions`, `rosterTypes`, `standingsTypes`, `pitchTypes`, `eventTypes`, `hitTrajectories`, `situationCodes`, `scheduleEventTypes`, `scheduleTypes`, `skyConditions`, `windDirection`, `languages`, `platforms`, `reviewReasons`, `logicalEvents`, `metrics`, `baseballStats`, `gameStatus`, `awards` (list), `jobTypes`, `sports`, `leagues`, `divisions`, `conferences`, `seasons?sportId={id}&all=true`/`seasons/all`.
Keys: `code`/`id` as returned. Status: todo.

### 1.2 Entities
| Dataset | Endpoint | Fan-out / params | Partition | Keys |
|---|---|---|---|---|
| `seasons` | `/v1/seasons/all?sportId={s}` | per sport | flat | `sport_id, season_id` |
| `sports` | `/v1/sports` | – | flat | `id` |
| `leagues` | `/v1/league?sportId={s}&seasons={y}` | per sport×season | season | `id, season` |
| `divisions` | `/v1/divisions?sportId={s}&season={y}` | per sport×season | season | `id, season` |
| `teams` | `/v1/teams?sportId={s}&season={y}&hydrate=venue,...` | per sport×season | season | `id, season` |
| `team_history` | `/v1/teams/history?teamIds={ids}` | per team | flat | `id, season` |
| `team_affiliates` | `/v1/teams/affiliates?teamIds={id}&season={y}` | per team×season | season | `id, season` |
| `team_coaches` | `/v1/teams/{id}/coaches?season={y}` | per team×season | season | `team_id, person_id, job` |
| `team_personnel` | `/v1/teams/{id}/personnel?season={y}` | per team×season | season | `team_id, person_id, job` |
| `team_alumni` | `/v1/teams/{id}/alumni?season={y}&group=...` | per team×season | season | `team_id, person_id` |
| `rosters_<type>` | `/v1/teams/{id}/roster?rosterType={type}&season={y}[&date=]` types: `active, 40Man, fullSeason, fullRoster, nonRosterInvitees, depthChart, gameday, coach` | per team×season×type | season | `team_id, person_id, roster_type, date` |
| `venues` | `/v1/venues?venueIds=all&hydrate=location,fieldInfo,timezone,...` and `/v1/venues/{id}` | – | flat | `id` |
| `people` | `/v1/people?personIds={ids}&hydrate=...` and `/v1/sports/{s}/players?season={y}` | per sport×season → ids | flat | `id` |
| `people_search` | `/v1/people/search?names={q}` | on demand | n/a | `id` |
| `people_changes` | `/v1/people/changes?updatedSince={ts}` | incremental sync | n/a | `id` |
| `free_agents` | `/v1/people/freeAgents?season={y}` | per season | season | `person_id, season` |
| `awards` / `award_recipients` | `/v1/awards`, `/v1/awards/{id}/recipients?season={y}` | per award×season | season | `award_id, season, person_id/team_id` |
| `attendance` | `/v1/attendance?teamId=&leagueId=&season=` | per season | season | `team_id, season, game_type` |
| `jobs_umpires` / `jobs_datacasters` / `jobs_official_scorers` | `/v1/jobs/umpires` etc. (`?date=`) | per season/date | flat/season | `person_id, job` |
| `draft` | `/v1/draft/{year}` | per year | season | `year, pick_overall` (plus `person_id`) |
| `draft_prospects` | `/v1/draft/prospects/{year}` | per year | season | `year, person_id` |
| `draft_latest` | `/v1/draft/{year}/latest` | on demand | n/a | – |
| `transactions` | `/v1/transactions?startDate=&endDate=` (and `?teamId=`) | per season windows | season | `transaction_id` |

### 1.3 Statistics
| Dataset | Endpoint | Fan-out | Partition | Keys |
|---|---|---|---|---|
| `stats_<statType>_<group>` | `/v1/stats?stats={statType}&group={hitting|pitching|fielding|catching|running|game|team|streak}&season={y}&playerPool=ALL&sportIds={s}&limit=…&offset=` (paginated) | per season×sport×statType×group (enumerate `statTypes`: `season, career, yearByYear, yearByYearAdvanced, seasonAdvanced, careerAdvanced, gameLog, byDateRange, byDateRangeAdvanced, byMonth, byDayOfWeek, homeAndAway, winLoss, statSplits, statSplitsAdvanced, projected, sabermetrics, expectedStatistics, winProbability, pitchArsenal, hotColdZones, sprayChart, playLog, tracking, vsPlayer, vsTeam, lastXGames, outsAboveAverage, ...` — **enumerate from `/v1/statTypes` and probe which combos return data**) | season | `person_id|team_id, season, stat_type, group, split` |
| `people_stats_<statType>_<group>` | `/v1/people/{id}/stats?stats=…&group=…&season=…` | per person (when league-wide `stats` cannot supply it, e.g. `gameLog`, `playLog`, `sprayChart`) | season | `person_id, season, ...` |
| `stats_leaders` | `/v1/stats/leaders?leaderCategories={cat}&season={y}&sportId={s}&statGroup=&limit=` | per season×leaderType | season | `category, season, rank, person_id/team_id` |
| `team_stats` | `/v1/teams/stats?stats=…&group=…&season=…&sportIds=` | per season×type×group | season | `team_id, season, ...` |
| `team_leaders` | `/v1/teams/{id}/leaders?leaderCategories=&season=` | per team×season | season | `team_id, category, rank` |
| `standings_<type>` | `/v1/standings?leagueId=103,104&season={y}&standingsTypes={type}&hydrate=team,division,league,...` types from `/v1/standingsTypes` (`regularSeason, wildCard, divisionLeaders, wildCardWithLeaders, firstHalf, secondHalf, springTraining, postseason, byDivision, byConference, byLeague, byOrganization`) | per season×type (and `date=` snapshots optional) | season | `season, team_id, type, as_of_date` |
| `home_run_derby` | `/v1/homeRunDerby/{gamePk}` (+ `/bracket`, `/pool`) | per HR-derby game | season | `game_pk, round, batter_id, swing` |
| `game_pace` | `/v1/gamePace?season=&sportId=` | per season | season | `season, ...` |
| `high_low` | `/v1/highLow/{team|player|game}?...` | per season | season | – |

### 1.4 Schedule & games
| Dataset | Endpoint | Fan-out | Partition | Keys |
|---|---|---|---|---|
| `schedule` (+ child tables) | `/v1/schedule?sportId={s}&season={y}&gameType={all}&hydrate=team,linescore,decisions,probablePitcher,officials,weather,venue,broadcasts,series,scoringplays,flags,lineups,tickets,game(content(summary,media(epg))),seriesStatus,review` (windows ≤ 31 days or full-season where the API allows) | per sport×season (all `gameType` codes: `S,R,F,D,L,W,C,N,P,A,I,E,...` from `/v1/gameTypes`) | season | `game_pk` |
| `schedule_postseason` / `_series` / `_tied` | `/v1/schedule/postseason`, `/postseason/series`, `/tied` | per season | season | `game_pk` / `series_id` |
| `game_feed_*` (11 tables, see change design §2) | `/v1.1/game/{pk}/feed/live` (final games) | per `game_pk` | season | `game_pk[, at_bat_index, event_index]` |
| `game_linescore` | `/v1/game/{pk}/linescore` | per game | season | `game_pk, inning` |
| `game_boxscore` | `/v1/game/{pk}/boxscore` | per game | season | `game_pk, team_id, person_id` |
| `game_play_by_play` | `/v1/game/{pk}/playByPlay` | per game | season | `game_pk, at_bat_index` |
| `game_win_probability` | `/v1/game/{pk}/winProbability` | per game | season | `game_pk, at_bat_index` |
| `game_context_metrics` | `/v1/game/{pk}/contextMetrics` | per game | season | `game_pk` |
| `game_content` | `/v1/game/{pk}/content` | per game | season | `game_pk, content_id` |
| `game_color` | `/v1/game/{pk}/feed/color` | per game | season | `game_pk, ts` |
| `game_changes` | `/v1/game/changes?updatedSince={ts}` | incremental | n/a | `game_pk` |
| `live_stream` | `/v1.1/game/{pk}/feed/live/timestamps`, `/feed/live/diffPatch?startTimecode=&endTimecode=` | streaming | n/a | `(game_pk, at_bat_index, event_index)` |

Minor-league coverage: all `sportId` values returned by `/v1/sports` (11 AAA, 12 AA, 13 High-A, 14 A, 15 Short-A, 16 Rookie, 17 Winter, 21–22, etc.) are included wherever the endpoint accepts `sportId`.
Hydrate lists and exact query params must be taken from live probing; `docs/sources/mlb_api.md` records the final ones.

---

## 2. Baseball Savant / Statcast — `https://baseballsavant.mlb.com` (2.5 req/s)

### 2.1 Pitch-level search
| Dataset | Endpoint | Params | Partition | Keys |
|---|---|---|---|---|
| `pitches` | `GET /statcast_search/csv` | `all=true&type=details&game_date_gt&game_date_lt&hfSea&hfGT={types}&player_type&sport_id&hfTeam…`; windows ≤ 5 days; **25,000-row cap → bisect**; 2008–present (PITCHf/x era 2008–2014 has fewer columns) | season | `game_pk, at_bat_number, pitch_number` |
| `game_feed_*` | `GET /gf?game_pk={pk}` | JSON per game (probe) | season | `game_pk, ...` |

### 2.2 Leaderboards — `GET /leaderboard/{route}?year=&type=&min=&csv=true` (all years from `min_year`, all type variants; "no qualifier" min where supported)
Registry targets (slug → route; verify each live, record `min_year`, variants, columns):
`expected_statistics` (batter/pitcher), `exit_velocity` (`/statcast`, batter/pitcher/batter-team/pitcher-team), `sprint_speed`, `running_splits`, `baserunning`/`baserunning-run-value`, `basestealing-run-value`, `bat_tracking` (+ `swing-path-attack-angle`, `batting-stance` if available), `outs_above_average` (fielder types), `directional_outs_above_average`, `outfield_jump` (`/outfield_jump`), `catch_probability`, `fielding-run-value`, `arm_strength`, `catcher_throwing`, `poptime`, `catcher_framing`, `catcher_blocking`, `pitch_arsenals` (avg speed/usage/spin), `pitch_arsenal_stats`, `pitch_movement`, `pitch_tempo`, `active_spin`, `spin_direction_pitches`, `percentile_rankings` (batter/pitcher), `home_runs`, `batted_ball`, `swing_take`, `abs_challenges`, `year_to_year`, `rolling`, `statcast_park_factors` (and `park-factor` variants), `custom` (arbitrary `selections=`), `pitch_timer`/`pitch_clock` if present, `bat_speed` variants.
Granularity per slug (player-season, player-pitchtype, team-season, game, rolling) recorded in `LeaderboardSpec`. Partition: season. Keys: documented per slug (e.g. `player_id, year, pitch_type`).

---

## 3. Lahman Baseball Database (`cbwinslow/lahman-database-csv` `data/*.csv`, pinned ref, 1871–2025; or user-supplied zip/dir via `import_archive`; no other source — never `chadwickbureau/baseballdatabank`)
27 tables, flat partition each, view `lahman_<table_lower>`; schema from real headers + `_extras`; PKs below (verify):

| Table | PK |
|---|---|
| AllstarFull | `playerID, yearID, gameNum, gameID` |
| Appearances | `yearID, teamID, playerID` |
| AwardsManagers | `playerID, awardID, yearID, lgID` |
| AwardsPlayers | `playerID, awardID, yearID, lgID` |
| AwardsShareManagers | `awardID, yearID, lgID, playerID` |
| AwardsSharePlayers | `awardID, yearID, lgID, playerID` |
| Batting | `playerID, yearID, stint` |
| BattingPost | `yearID, round, playerID` |
| CollegePlaying | `playerID, schoolID, yearID` |
| Fielding | `playerID, yearID, stint, POS` |
| FieldingOF | `playerID, yearID, stint` |
| FieldingOFsplit | `playerID, yearID, stint, POS` |
| FieldingPost | `playerID, yearID, round, POS` |
| HallOfFame | `playerID, yearID, votedBy` |
| HomeGames | `yearkey, leaguekey, teamkey, parkkey` |
| Managers | `yearID, teamID, inseason` |
| ManagersHalf | `yearID, teamID, half, playerID` |
| Parks | `parkkey` |
| People | `playerID` |
| Pitching | `playerID, yearID, stint` |
| PitchingPost | `yearID, round, playerID` |
| Salaries | `yearID, teamID, lgID, playerID` |
| Schools | `schoolID` |
| SeriesPost | `yearID, round` |
| Teams | `yearID, lgID, teamID` |
| TeamsFranchises | `franchID` |
| TeamsHalf | `yearID, lgID, teamID, Half` |

(Any additional tables/files present in the mirror tree at the pinned ref are ingested as `lahman_<stem>` datasets with inferred-then-reviewed schemas.)

---

## 4. Chadwick Bureau Register — `chadwickbureau/register` (pinned SHA, revalidated every 24 h)
| Dataset | Files (discover via tree) | Keys |
|---|---|---|
| `register` | `data/people-0.csv … people-f.csv` (16 shards) | `key_person` (unique), `key_uuid` |
| `register_names` | `data/names.csv` (if present) | `key_person, name_type, name_*` |
| `register_links` | `data/links.csv` (if present) | `key_person, link_type, link_url` |
Views: `chadwick_register` plus `v_player_crosswalk` (MLBAM ↔ Retrosheet ↔ BBRef ↔ FanGraphs ↔ Lahman via `People.retroID/bbrefID`).

---

## 5. Retrosheet — `chadwickbureau/retrosheet` (pinned SHA; tree discovery via GitHub API; never `retrosheet.org` for bulk)
Datasets (raw = files as published; processed = typed Parquet). All seasons present in the tree (event files from 1912 where available; game logs from 1871).
| Dataset | Source files (patterns confirmed from tree) | Partition | Keys |
|---|---|---|---|
| `event_files` (raw only) | regular `*.EVA/*.EVN`, postseason/all-star `*.EVE`, `TEAM{year}` | season | file name |
| `events` | parsed regular-season events (98-column schema) | season | `game_id, event_id` |
| `events_postseason` | parsed postseason/all-star events | season | `game_id, event_id` |
| `boxscore_batting` / `boxscore_pitching` | derived from event files (chadwickpy `cwbox`) | season | `game_id, player_id` |
| `box_files` + parsed `box_*` | `box/` directory files (parse if format supported; else raw only with documented reason) | season | `game_id, ...` |
| `daily_splits` | derived (`cwdaily`, 154 columns) | season | `game_id, player_id, appear_dt` |
| `substitutions` | derived (`cwsub`, 26 columns) | season | `game_id, event_id` |
| `rosters` | `*.ROS` | season | `team_id, player_id, season` |
| `gamelogs` | `GL{year}.TXT` / `gl{year}.txt` (161 columns, header-less, positional by documented spec) | season | `date, game_number, home_team, visiting_team` |
| `gamelogs_postseason` | `GLWC/GLDV/GLLC/GLWS/GLAS.TXT` (and any others in tree) | flat | same |
| `schedule` | `schedule/` files | season | `date, game_number, home, visitor` |
| `reference_<stem>` | every CSV in `reference/` (known: `ballparks, teams, ejections, coaches, relatives, biofile`; discover others such as umpires, franchises, etc.) | flat | per file |
| `misc_<stem>` | files in `misc/` if tabular | flat | per file |

---

## 6. Discovery & verification procedure (executor checklist)
1. `scripts/probe_endpoints.py` iterates this catalog's machine-readable twin `docs/endpoint_catalog.yaml` (generate from this file; one record per dataset with `source, dataset, url_template, params, fan_out, partition, keys, status`) and, for each, performs a minimal live call, records `{status_code, bytes, sample_columns, elapsed}` into `docs/endpoint_probe.json`.
2. Update `Status`/`Verified on` here and in `docs/sources/*.md`.
3. For GitHub-hosted sources, fetch the tree via `GET https://api.github.com/repos/{owner}/{repo}/git/trees/{ref}?recursive=1` and diff against the registry; any file pattern not covered by a dataset is a coverage gap to be added (or documented as intentionally excluded with a reason).
4. For MLB, diff discovered meta lists (`/v1/statTypes`, `/v1/gameTypes`, `/v1/standingsTypes`, `/v1/leagueLeaderTypes`, `/v1/rosterTypes`, `/v1/sports`) against the registry; every enumerated value must have a dataset/variant or an explicit exclusion.
5. `baseballpy catalog status` must show zero `MISSING` datasets for a full `ingest all` run (excluding rows marked `unsupported`).
