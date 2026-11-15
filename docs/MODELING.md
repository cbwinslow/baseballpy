# Machine Learning & Modeling Guide

Start-here guide for training ML models on `baseballpy` lake tables and DuckDB views.

## 1. Data Sources & Dimensions

Dimensions verified on the lake (`docs/sources/` and `src/baseballpy/database.py`):

- **Statcast Pitches (`statcast_pitches` / `v_pitches_unique`):** 15.0M pitches (2008–2026), key `(game_pk, at_bat_number, pitch_number)`. Tracking from 2015, bat tracking from 2024 (`docs/sources/statcast.md`). `v_pitches_unique` deduplicates 2026 repeated rows (ADR 119).
- **Retrosheet Events (`retrosheet_events`):** 15.8M events (1908–2025), key `(GAME_ID, EVENT_ID)`. Complete base-out states, lineup substitutions, and official scoring codes (`docs/sources/retrosheet.md`). Overlaps Statcast 2008–2025.
- **Chadwick Crosswalk (`v_player_crosswalk`):** 526k player identities, key `key_person` / `key_mlbam`. Bridges MLBAM, Retrosheet (`key_retro`), BBRef, and FanGraphs (`docs/sources/chadwick.md`, `src/baseballpy/database.py`).
- **Game Crosswalk (`v_game_crosswalk`):** Bridges MLBAM schedule `game_pk` to Retrosheet `retro_game_id`, official dates, doubleheaders, and ballparks (`src/baseballpy/database.py`).
- **MLB Gameday Plays (`mlb_game_feed_plays`):** Live play-by-play feeds (2008–2026), key `(game_pk, about_at_bat_index)`. Play results, innings and scoring context (win probability is a separate dataset, `game_win_probability`) (`docs/sources/mlb_api.md`).

## 2. Cross-Source Join Recipes

### Recipe 1: Statcast Pitch to Player Names (via Crosswalk)
Join `statcast_pitches` (or `v_pitches_unique`) on `batter` and `pitcher` (MLBAM IDs) to `v_player_crosswalk` (`src/baseballpy/database.py`):
```sql
SELECT p.game_pk, p.at_bat_number, p.pitch_number, p.game_date,
       b.name_first || ' ' || b.name_last AS batter_name,
       pit.name_first || ' ' || pit.name_last AS pitcher_name,
       b.key_retro AS batter_retro_id, pit.key_retro AS pitcher_retro_id
FROM v_pitches_unique p
LEFT JOIN v_player_crosswalk b ON p.batter = b.key_mlbam
LEFT JOIN v_player_crosswalk pit ON p.pitcher = pit.key_mlbam;
```

### Recipe 2: Statcast Plate Appearance to Retrosheet Event
Statcast has no `GAME_ID` and Retrosheet has no `game_pk`. Join games via `v_game_crosswalk` and pair the n-th PA in each source (caveat: pair only games with equal PA counts, verified in `scripts/join_coverage.py`):
```sql
WITH sc_pa AS (
    SELECT p.game_pk, p.at_bat_number, min(p.batter) AS batter, min(p.pitcher) AS pitcher,
           row_number() OVER (PARTITION BY p.game_pk ORDER BY p.at_bat_number) AS pa_seq,
           count(DISTINCT p.at_bat_number) OVER (PARTITION BY p.game_pk) AS pa_total
    FROM v_pitches_unique p GROUP BY p.game_pk, p.at_bat_number
),
retro_pa AS (
    SELECT e.GAME_ID, e.EVENT_ID, e.BAT_ID, e.PIT_ID, e.EVENT_CD,
           row_number() OVER (PARTITION BY e.GAME_ID ORDER BY e.EVENT_ID) AS pa_seq,
           count(*) OVER (PARTITION BY e.GAME_ID) AS pa_total
    FROM retrosheet_events e WHERE e.BAT_EVENT_FL = 'T'
)
SELECT gx.game_date, sc.game_pk, r.GAME_ID, sc.pa_seq, sc.batter, r.BAT_ID, r.EVENT_CD
FROM v_game_crosswalk gx
JOIN sc_pa sc ON gx.game_pk = sc.game_pk
JOIN retro_pa r ON gx.retro_game_id = r.GAME_ID AND sc.pa_seq = r.pa_seq
WHERE sc.pa_total = r.pa_total;  -- Equal-count caveat: omit games with unaligned PAs
```

Measured with `scripts/join_coverage.py --season 2023` on 2026-11-14: all 2,430 Retrosheet games join to a Statcast game through the crosswalk; 2,080 of them (85.6%) have the same number of plate appearances in both sources, and in those games 158,019 paired plate appearances agree on the batter 99.99% of the time and on the pitcher 99.98%. Statcast also holds spring-training and exhibition games that Retrosheet does not, and 1,234 of its 3,362 players have no `key_retro` in the register (mostly players who never reached the majors), so keep the equal-count filter and expect to lose about 14% of games with this recipe.

### Recipe 3: Statcast Pitch to MLB Feed Play
Statcast `at_bat_number` is 1-indexed; MLB Gameday `about_at_bat_index` is 0-indexed (checked on 2024 data: `at_bat_number = about_at_bat_index + 1`):
```sql
SELECT p.game_pk, p.at_bat_number, p.pitch_number, p.pitch_type, p.release_speed,
       f.result_event, f.result_description, f.about_inning, f.about_is_scoring_play
FROM v_pitches_unique p
JOIN mlb_game_feed_plays f
  ON p.game_pk = f.game_pk AND p.at_bat_number = f.about_at_bat_index + 1;
```

## 3. Reading Data (DuckDB, Polars, pandas)

Access patterns from `docs/QUICKSTART.md`, `src/baseballpy/access.py`, and `src/baseballpy/database.py`:
```python
import baseballpy as bp
from baseballpy.database import connect_db

# 1. DuckDB SQL: fast serverless analytics over synced lake views
df_sql = bp.sql(
    "SELECT pitch_type, avg(release_speed) v FROM v_pitches_unique WHERE season = 2024 GROUP BY 1"
)
# or direct read-only DuckDB connection: con = connect_db(read_only=True)

# 2. Polars: direct multi-threaded Parquet reader (use lazy=True for query pruning)
df_pl = bp.read(
    "statcast.pitches", seasons=2024, columns=["game_pk", "release_speed", "plate_x", "plate_z"]
)

# 3. pandas: zero-copy conversion from PyArrow lake tables
df_pd = bp.read(
    "statcast.pitches", seasons=2024, columns=["game_date", "delta_run_exp"], backend="pandas"
)
```

## 4. Leakage Warnings for Modeling

- **Temporal Splits:** Always split by `game_date` (e.g. train on April–July, test on August–September; or train on 2021–2023, test on 2024). Never use random cross-validation or row splits: random splits leak pitcher form, tactical shifts, and pitch sequences across train and test.
- **Outcome Column Leakage:** The following columns measure event results and MUST NOT be used as features:
  - Run / Win Expectancy: `delta_run_exp`, `delta_home_win_exp`
  - Linear Weights: `woba_value`, `woba_denom`, `babip_value`, `iso_value`, `estimated_ba_using_speedangle`, `estimated_woba_using_speedangle`
  - Play Outcomes: `events`, `description`, `des`
  - Post-play scores: `post_home_score`, `post_away_score`, `post_bat_score`, `post_fld_score`
- **Pre-Pitch Horizon:** In pitch quality or whiff models, batted-ball tracking (`launch_speed`, `launch_angle`, `bb_type`, `hit_distance_sc`) occurs after the swing and must be excluded.

## 5. Three Modeling Starters

### Starter 1: Expected Run Value (Pitch Quality / "Stuff" & "Location")
Predicts run expectancy impact `delta_run_exp` from pre-pitch ball kinematics and location:
```sql
SELECT game_date, release_speed, release_spin_rate, release_extension, pfx_x, pfx_z,
       plate_x, plate_z, vx0, vy0, vz0, ax, ay, az, balls, strikes, stand, p_throws,
       delta_run_exp AS target_run_value
FROM v_pitches_unique
WHERE season BETWEEN 2021 AND 2024
  AND release_speed IS NOT NULL AND plate_x IS NOT NULL AND delta_run_exp IS NOT NULL;
```

### Starter 2: Swing-and-Miss (Whiff) Probability
Predicts whiff probability conditioned on a swing (`description` in swinging strikes, fouls, or balls in play):
```sql
SELECT game_date, release_speed, release_spin_rate, release_extension, pfx_x, pfx_z,
       plate_x, plate_z, balls, strikes, stand, p_throws,
       CASE WHEN description IN ('swinging_strike', 'swinging_strike_blocked') THEN 1 ELSE 0 END AS is_whiff
FROM v_pitches_unique
WHERE season BETWEEN 2021 AND 2024
  AND description IN ('swinging_strike', 'swinging_strike_blocked', 'foul', 'foul_tip', 'hit_into_play')
  AND plate_x IS NOT NULL;
```

### Starter 3: Batted-Ball xwOBA (Contact Quality)
Predicts `woba_value` on balls in play (`type = 'X'`) from launch velocity, launch angle, and spray:
```sql
SELECT game_date, launch_speed, launch_angle, hc_x, hc_y, stand,
       woba_value AS target_woba
FROM v_pitches_unique
WHERE season BETWEEN 2021 AND 2024
  AND type = 'X' AND launch_speed IS NOT NULL AND launch_angle IS NOT NULL AND woba_value IS NOT NULL;
```
