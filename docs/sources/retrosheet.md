# Retrosheet Endpoint & Dataset Catalog

## Upstream Overview
- **Provider:** Retrosheet (`retrosheet.org`) & Chadwick Baseball Bureau GitHub Mirror
- **Primary Extraction Source:** Fastly-backed GitHub raw mirror (`https://raw.githubusercontent.com/chadwickbureau/retrosheet/master/`)
- **Rate Limit Policy:** Max 15 requests/second (token bucket bounded)
- **Anti-Scraping Policy:** `retrosheet.org` drops TCP SYN connections on automated bulk queries; all bulk historical extractions route exclusively through GitHub mirrors (ADR 1 & ADR 5).
- **Processing Engine:** `chadwickpy` (pure Python port of the Chadwick C tools suite)

---

## Datasets Covered

### 1. Play-by-Play Event Data (`.EVA`, `.EVN`, `.EVE`, `.EB*`)
- **Coverage:** Regular season, Postseason (Wild Card, ALDS/NLDS, ALCS/NLCS, World Series), and All-Star Games (1921–present).
- **Format:** Retrosheet DiamondWare event records parsed via `chadwickpy.tools.events.event_rows` into 97 canonical fields.
- **Physical Type:** PyArrow Table partitioned by `season={year}`.

#### Key Event Columns (97 Fields)
| Column Name | PyArrow Physical Type | Nullable | Example Raw Value | Description |
| :--- | :--- | :---: | :--- | :--- |
| `game_id` | `string()` | No | `BOS202304010` | 12-character unique game identifier |
| `away_team_id` | `dictionary(int8, string)` | No | `BAL` | Visiting team 3-letter code |
| `inn_ct` | `int8()` | No | `1` | Inning number |
| `bat_home_id` | `int8()` | No | `0` | Batting team (0 = away, 1 = home) |
| `outs_ct` | `int8()` | No | `0` | Number of outs prior to event (0, 1, 2) |
| `balls_ct` | `int8()` | No | `3` | Balls prior to event |
| `strikes_ct` | `int8()` | No | `2` | Strikes prior to event |
| `pitch_seq_tx` | `string()` | Yes | `CBFFBX` | Pitch sequence codes |
| `away_score_ct` | `int16()` | No | `0` | Visiting team score prior to play |
| `home_score_ct` | `int16()` | No | `0` | Home team score prior to play |
| `resp_bat_id` | `string()` | No | `mullc001` | Responsible batter 8-character ID |
| `resp_pit_id` | `string()` | No | `klubc001` | Responsible pitcher 8-character ID |
| `base1_run_id` | `string()` | Yes | `rutsa001` | Runner on 1st base |
| `base2_run_id` | `string()` | Yes | `null` | Runner on 2nd base |
| `base3_run_id` | `string()` | Yes | `null` | Runner on 3rd base |
| `event_tx` | `string()` | No | `HR/9/F` | Raw Retrosheet play description string |
| `event_cd` | `int8()` | No | `23` | Numerical play code (23 = home run) |
| `bat_dest_id` | `int8()` | No | `4` | Batter final base destination (0-4) |
| `run1_dest_id` | `int8()` | No | `0` | Runner 1 final base destination |
| `run2_dest_id` | `int8()` | No | `0` | Runner 2 final base destination |
| `run3_dest_id` | `int8()` | No | `0` | Runner 3 final base destination |

---

### 2. Historical Game Logs (1871–present)
- **Regular Season:** `GL1871.TXT` through `GL2024.TXT`.
- **Postseason Archives:** `GLWC.TXT` (Wild Card), `GLDV.TXT` (Division Series), `GLLC.TXT` (League Championship Series), `GLWS.TXT` (World Series), `GLAS.TXT` (All-Star Games).
- **Format:** 161 standard comma-separated fields per game.

#### Game Log Column Dictionary (161 Columns)
- `date`: `date32()` — Official game date (`YYYY-MM-DD`).
- `game_num`: `int8()` — Game number (0 for single game, 1 or 2 for doubleheader).
- `day_of_week`: `dictionary(int8, string)` — Mon, Tue, Wed, Thu, Fri, Sat, Sun.
- `v_team`, `h_team`: `dictionary(int8, string)` — Visiting and home team abbreviations.
- `v_league`, `h_league`: `dictionary(int8, string)` — League codes (`AL`, `NL`, `AA`, `PL`, `FL`, `NA`).
- `v_game_num`, `h_game_num`: `int16()` — Team's season game number.
- `v_score`, `h_score`: `int16()` — Final runs scored.
- `outs_total`: `int16()` — Total length in outs (e.g., 54 for 9-inning game).
- `day_night`: `dictionary(int8, string)` — Day (`D`) or Night (`N`).
- `completion`: `string()` — Suspended game continuation information.
- `forfeit`: `string()` — Forfeit details if applicable.
- `protest`: `string()` — Official protest details.
- `park_id`: `string()` — Retrosheet 5-character ballpark ID.
- `attendance`: `int32()` — Paid attendance.
- `time_of_game`: `int16()` — Game duration in minutes.
- `v_line_score`, `h_line_score`: `string()` — Inning-by-inning line score string.
- Detailed offensive, pitching, and defensive statistics for visiting and home teams (at-bats, hits, doubles, triples, home runs, RBI, SH, SF, HBP, walks, intentional walks, strikeouts, stolen bases, caught stealing, grounded into double plays, catcher interference, left on base, pitchers used, individual earned runs, team earned runs, wild pitches, balks, putouts, assists, errors, passed balls, double plays, triple plays).
- Umpire IDs: `hp_ump_id`, `hp_ump_name`, `1b_ump_id`, `1b_ump_name`, `2b_ump_id`, `2b_ump_name`, `3b_ump_id`, `3b_ump_name`, `lf_ump_id`, `lf_ump_name`, `rf_ump_id`, `rf_ump_name`.
- Manager IDs: `v_manager_id`, `v_manager_name`, `h_manager_id`, `h_manager_name`.
- Pitchers of Record: `win_pitcher_id`, `win_pitcher_name`, `lose_pitcher_id`, `lose_pitcher_name`, `save_pitcher_id`, `save_pitcher_name`, `gwrbi_id`, `gwrbi_name`.
- Starting Pitchers: `v_start_pitcher_id`, `v_start_pitcher_name`, `h_start_pitcher_id`, `h_start_pitcher_name`.
- Starting Lineups: Visiting and home players 1–9, including player IDs, names, and defensive positions (1–10).

---

### 3. Box Scores (`cwbox`)
Generated via `chadwickpy.tools.cwbox.box_create` into two primary tables:

#### A. Batting Box Score Table (`retrosheet_box_batting`)
| Column Name | PyArrow Physical Type | Nullable | Description |
| :--- | :--- | :---: | :--- |
| `game_id` | `string()` | No | Unique game identifier (`BOS202304010`) |
| `team_id` | `dictionary(int8, string)` | No | Team abbreviation |
| `player_id` | `string()` | No | 8-character player ID |
| `player_name` | `string()` | No | Player full name |
| `slot` | `int8()` | No | Lineup slot (1–9, or 0 for substitute/pitcher in AL) |
| `pos` | `int8()` | No | Defensive position (1 = P, 2 = C, ..., 9 = RF, 10 = DH, 11 = PH, 12 = PR) |
| `ab` | `int16()` | No | At-bats |
| `r` | `int16()` | No | Runs scored |
| `h` | `int16()` | No | Hits |
| `d` | `int16()` | No | Doubles (2B) |
| `t` | `int16()` | No | Triples (3B) |
| `hr` | `int16()` | No | Home runs |
| `rbi` | `int16()` | No | Runs batted in |
| `bb` | `int16()` | No | Base on balls |
| `ibb` | `int16()` | No | Intentional walks |
| `so` | `int16()` | No | Strikeouts |
| `hbp` | `int16()` | No | Hit by pitch |
| `sh` | `int16()` | No | Sacrifice hits |
| `sf` | `int16()` | No | Sacrifice flies |
| `sb` | `int16()` | No | Stolen bases |
| `cs` | `int16()` | No | Caught stealing |
| `gidp` | `int16()` | No | Grounded into double play |

#### B. Pitching Box Score Table (`retrosheet_box_pitching`)
| Column Name | PyArrow Physical Type | Nullable | Description |
| :--- | :--- | :---: | :--- |
| `game_id` | `string()` | No | Unique game identifier |
| `team_id` | `dictionary(int8, string)` | No | Team abbreviation |
| `pitcher_id` | `string()` | No | 8-character pitcher ID |
| `pitcher_name` | `string()` | No | Pitcher full name |
| `starter_fl` | `bool_()` | No | True if starting pitcher, False if relief |
| `seq` | `int8()` | No | Pitcher entrance sequence order (1 = starter, 2 = 1st reliever, ...) |
| `outs_recorded` | `int16()` | No | Total outs recorded (divide by 3 for IP) |
| `bf` | `int16()` | No | Batters faced |
| `h` | `int16()` | No | Hits allowed |
| `r` | `int16()` | No | Runs allowed |
| `er` | `int16()` | No | Earned runs allowed |
| `bb` | `int16()` | No | Walks allowed |
| `ibb` | `int16()` | No | Intentional walks allowed |
| `so` | `int16()` | No | Strikeouts thrown |
| `hr` | `int16()` | No | Home runs allowed |
| `hbp` | `int16()` | No | Hit batsmen |
| `wp` | `int16()` | No | Wild pitches |
| `bk` | `int16()` | No | Balks |
| `pitches` | `int16()` | Yes | Total pitches thrown (if tracked) |
| `strikes` | `int16()` | Yes | Total strikes thrown (if tracked) |

---

### 4. Daily Player Splits (`daily`)
Generated via `chadwickpy.tools.daily.daily_lines`:
- Table of daily lines per player per game contest across batting, pitching, and fielding appearances.
- Columns: `game_id`, `game_date`, `player_id`, `team_id`, `opponent_id`, `home_fl`, `slot`, `pos`, `ab`, `r`, `h`, `d`, `t`, `hr`, `rbi`, `bb`, `so`, `po`, `a`, `e`, `ip_outs`.

---

### 5. Substitutions (`sub`)
Generated via `chadwickpy.tools.sub.sub_lines`:
- In-game substitutions and lineup shifts.
- Columns: `game_id`, `inning`, `event_num`, `team_id`, `player_id`, `slot`, `pos`, `removed_player_id`, `removed_pos`.

---

### 6. Reference Directories (`reference/`)

#### A. Ballparks (`reference/ballparks.csv`)
| Column Name | PyArrow Physical Type | Nullable | Description |
| :--- | :--- | :---: | :--- |
| `park_id` | `string()` | No | 5-character park code (e.g., `BOS07`) |
| `name` | `string()` | No | Official stadium name (e.g., `Fenway Park`) |
| `aka` | `string()` | Yes | Alternate names / corporate sponsor names |
| `city` | `string()` | No | City |
| `state` | `string()` | No | State or Province code |
| `start_date` | `date32()` | Yes | Opening contest date |
| `end_date` | `date32()` | Yes | Final contest date (null if active) |
| `league` | `string()` | Yes | Primary league affiliation |
| `notes` | `string()` | Yes | Historical notes, demolition details |

#### B. Teams (`reference/teams.csv`)
| Column Name | PyArrow Physical Type | Nullable | Description |
| :--- | :--- | :---: | :--- |
| `team_id` | `string()` | No | 3-letter team code (`BOS`) |
| `league` | `string()` | No | League code (`AL`, `NL`) |
| `city` | `string()` | No | Team city |
| `nickname` | `string()` | No | Mascot / franchise nickname (`Red Sox`) |
| `first_year` | `int16()` | No | Franchise inaugural year |
| `last_year` | `int16()` | No | Final active year (or current season) |

#### C. Ejections (`reference/ejections.csv`)
| Column Name | PyArrow Physical Type | Nullable | Description |
| :--- | :--- | :---: | :--- |
| `game_id` | `string()` | No | Retrosheet game ID |
| `date` | `date32()` | No | Contest date |
| `game_num` | `int8()` | No | Game number (0, 1, 2) |
| `ejected_id` | `string()` | No | 8-character ID of ejected person |
| `ejected_name` | `string()` | No | Ejected individual's name |
| `team_id` | `string()` | No | Team code of ejectee |
| `role` | `dictionary(int8, string)` | No | Role (`P` player, `M` manager, `C` coach, `T` trainer) |
| `umpire_id` | `string()` | No | Retrosheet ID of ejecting umpire |
| `umpire_name` | `string()` | No | Ejecting umpire's name |
| `inning` | `int8()` | No | Inning of ejection |
| `reason` | `string()` | No | Official ejection reason / disputed call |

#### D. Coaching Staffs (`reference/coaches.csv`)
- Columns: `coach_id`, `last_name`, `first_name`, `season`, `team_id`, `role` (Manager, Bench, Pitching, Hitting, 1B, 3B, Bullpen).

#### E. Relatives (`reference/relatives.csv`)
- Columns: `player_id_1`, `player_id_2`, `relation` (father-son, brothers, grandfather-grandson, uncle-nephew, cousins).

#### F. Biographical File (`reference/biofile.csv`)
- Columns: `player_id`, `name_last`, `name_first`, `birth_date`, `birth_city`, `birth_state`, `birth_country`, `death_date`, `bats`, `throws`, `height`, `weight`, `debut_date`, `final_game_date`, `college`, `high_school`.
