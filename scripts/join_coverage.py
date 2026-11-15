"""Reusable cross-source join-coverage verification report.

Evaluates coverage and identity agreement across Statcast pitches, Retrosheet
events, and the Chadwick player crosswalk using DuckDB view catalog connections.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import duckdb

from baseballpy.database import connect_db

#: Counts games in Statcast, games in Retrosheet, and games joined via v_game_crosswalk for a season.
GAMES_COVERAGE_QUERY = """
WITH sc_games AS (
    SELECT DISTINCT game_pk
    FROM statcast_pitches
    WHERE season = ?
),
retro_games AS (
    SELECT DISTINCT GAME_ID AS retro_game_id
    FROM retrosheet_events
    WHERE season = ?
),
joined_games AS (
    SELECT DISTINCT gx.game_pk, gx.retro_game_id
    FROM v_game_crosswalk gx
    JOIN sc_games sc ON gx.game_pk = sc.game_pk
    JOIN retro_games rg ON gx.retro_game_id = rg.retro_game_id
    WHERE gx.season = ?
)
SELECT
    (SELECT count(*) FROM sc_games) AS games_statcast,
    (SELECT count(*) FROM retro_games) AS games_retrosheet,
    (SELECT count(*) FROM joined_games) AS games_joined;
"""

#: Counts plate appearances in Statcast and Retrosheet for joined games, and games with equal PA counts.
PA_COVERAGE_QUERY = """
WITH sc_games AS (
    SELECT DISTINCT game_pk
    FROM statcast_pitches
    WHERE season = ?
),
retro_games AS (
    SELECT DISTINCT GAME_ID AS retro_game_id
    FROM retrosheet_events
    WHERE season = ?
),
joined_games AS (
    SELECT DISTINCT gx.game_pk, gx.retro_game_id
    FROM v_game_crosswalk gx
    JOIN sc_games sc ON gx.game_pk = sc.game_pk
    JOIN retro_games rg ON gx.retro_game_id = rg.retro_game_id
    WHERE gx.season = ?
),
sc_pa AS (
    SELECT
        p.game_pk,
        count(DISTINCT p.at_bat_number) AS pa_count
    FROM statcast_pitches p
    JOIN joined_games jg ON p.game_pk = jg.game_pk
    WHERE p.season = ?
    GROUP BY p.game_pk
),
retro_pa AS (
    SELECT
        e.GAME_ID AS retro_game_id,
        count(*) AS pa_count
    FROM retrosheet_events e
    JOIN joined_games jg ON e.GAME_ID = jg.retro_game_id
    WHERE e.season = ? AND e.BAT_EVENT_FL = 'T'
    GROUP BY e.GAME_ID
),
paired_games AS (
    SELECT
        jg.game_pk,
        jg.retro_game_id,
        coalesce(sc.pa_count, 0) AS sc_pa_count,
        coalesce(r.pa_count, 0) AS retro_pa_count
    FROM joined_games jg
    LEFT JOIN sc_pa sc ON jg.game_pk = sc.game_pk
    LEFT JOIN retro_pa r ON jg.retro_game_id = r.retro_game_id
)
SELECT
    coalesce(sum(sc_pa_count), 0) AS statcast_pa,
    coalesce(sum(retro_pa_count), 0) AS retrosheet_pa,
    count(*) AS total_joined_games,
    count(*) FILTER (WHERE sc_pa_count = retro_pa_count) AS games_equal_pa
FROM paired_games;
"""

#: For joined games with equal PA counts, pairs n-th PA in both sources and counts batter and pitcher matches.
PA_AGREEMENT_QUERY = """
WITH sc_games AS (
    SELECT DISTINCT game_pk
    FROM statcast_pitches
    WHERE season = ?
),
retro_games AS (
    SELECT DISTINCT GAME_ID AS retro_game_id
    FROM retrosheet_events
    WHERE season = ?
),
joined_games AS (
    SELECT DISTINCT gx.game_pk, gx.retro_game_id
    FROM v_game_crosswalk gx
    JOIN sc_games sc ON gx.game_pk = sc.game_pk
    JOIN retro_games rg ON gx.retro_game_id = rg.retro_game_id
    WHERE gx.season = ?
),
sc_game_pa_counts AS (
    SELECT
        p.game_pk,
        count(DISTINCT p.at_bat_number) AS pa_count
    FROM statcast_pitches p
    JOIN joined_games jg ON p.game_pk = jg.game_pk
    WHERE p.season = ?
    GROUP BY p.game_pk
),
retro_game_pa_counts AS (
    SELECT
        e.GAME_ID AS retro_game_id,
        count(*) AS pa_count
    FROM retrosheet_events e
    JOIN joined_games jg ON e.GAME_ID = jg.retro_game_id
    WHERE e.season = ? AND e.BAT_EVENT_FL = 'T'
    GROUP BY e.GAME_ID
),
equal_games AS (
    SELECT jg.game_pk, jg.retro_game_id
    FROM joined_games jg
    JOIN sc_game_pa_counts sc ON jg.game_pk = sc.game_pk
    JOIN retro_game_pa_counts rg ON jg.retro_game_id = rg.retro_game_id
    WHERE sc.pa_count = rg.pa_count
),
sc_pa_ordered AS (
    SELECT
        p.game_pk,
        p.at_bat_number,
        min(p.batter) AS batter_mlbam,
        min(p.pitcher) AS pitcher_mlbam,
        row_number() OVER (PARTITION BY p.game_pk ORDER BY p.at_bat_number) AS pa_seq
    FROM statcast_pitches p
    JOIN equal_games eg ON p.game_pk = eg.game_pk
    WHERE p.season = ?
    GROUP BY p.game_pk, p.at_bat_number
),
retro_pa_ordered AS (
    SELECT
        e.GAME_ID AS retro_game_id,
        e.EVENT_ID,
        e.BAT_ID,
        e.PIT_ID,
        row_number() OVER (PARTITION BY e.GAME_ID ORDER BY e.EVENT_ID) AS pa_seq
    FROM retrosheet_events e
    JOIN equal_games eg ON e.GAME_ID = eg.retro_game_id
    WHERE e.season = ? AND e.BAT_EVENT_FL = 'T'
),
player_crosswalk_dedup AS (
    SELECT
        key_mlbam,
        any_value(key_retro) AS key_retro
    FROM v_player_crosswalk
    WHERE key_mlbam IS NOT NULL AND key_retro IS NOT NULL
    GROUP BY key_mlbam
),
paired_pa AS (
    SELECT
        eg.game_pk,
        eg.retro_game_id,
        sc.pa_seq,
        sc.batter_mlbam,
        sc.pitcher_mlbam,
        cx_bat.key_retro AS sc_batter_retro,
        cx_pit.key_retro AS sc_pitcher_retro,
        r.BAT_ID AS retro_bat_id,
        r.PIT_ID AS retro_pit_id
    FROM equal_games eg
    JOIN sc_pa_ordered sc ON eg.game_pk = sc.game_pk
    JOIN retro_pa_ordered r ON eg.retro_game_id = r.retro_game_id AND sc.pa_seq = r.pa_seq
    LEFT JOIN player_crosswalk_dedup cx_bat ON sc.batter_mlbam = cx_bat.key_mlbam
    LEFT JOIN player_crosswalk_dedup cx_pit ON sc.pitcher_mlbam = cx_pit.key_mlbam
)
SELECT
    count(*) AS total_equal_game_pa,
    count(*) FILTER (WHERE sc_batter_retro IS NOT NULL AND sc_batter_retro = retro_bat_id) AS batter_matches,
    count(*) FILTER (WHERE sc_pitcher_retro IS NOT NULL AND sc_pitcher_retro = retro_pit_id) AS pitcher_matches,
    CASE WHEN count(*) > 0
        THEN round(count(*) FILTER (WHERE sc_batter_retro IS NOT NULL AND sc_batter_retro = retro_bat_id) * 1.0 / count(*), 4)
        ELSE 0.0 END AS batter_agreement_rate,
    CASE WHEN count(*) > 0
        THEN round(count(*) FILTER (WHERE sc_pitcher_retro IS NOT NULL AND sc_pitcher_retro = retro_pit_id) * 1.0 / count(*), 4)
        ELSE 0.0 END AS pitcher_agreement_rate
FROM paired_pa;
"""

#: Counts distinct Statcast players (batters/pitchers) in a season lacking a key_retro crosswalk entry.
UNMAPPED_PLAYERS_QUERY = """
WITH sc_players AS (
    SELECT DISTINCT batter AS player_mlbam
    FROM statcast_pitches
    WHERE season = ?
    UNION
    SELECT DISTINCT pitcher AS player_mlbam
    FROM statcast_pitches
    WHERE season = ?
),
retro_map AS (
    SELECT
        key_mlbam,
        any_value(key_retro) AS key_retro
    FROM v_player_crosswalk
    WHERE key_mlbam IS NOT NULL
    GROUP BY key_mlbam
)
SELECT
    count(*) AS total_statcast_players,
    count(*) FILTER (WHERE rm.key_retro IS NULL) AS unmapped_players
FROM sc_players p
LEFT JOIN retro_map rm ON p.player_mlbam = rm.key_mlbam;
"""

#: Retrieves specific unmapped Statcast player IDs (if any) with no key_retro crosswalk entry.
UNMAPPED_PLAYER_IDS_QUERY = """
WITH sc_players AS (
    SELECT DISTINCT batter AS player_mlbam
    FROM statcast_pitches
    WHERE season = ?
    UNION
    SELECT DISTINCT pitcher AS player_mlbam
    FROM statcast_pitches
    WHERE season = ?
),
retro_map AS (
    SELECT
        key_mlbam,
        any_value(key_retro) AS key_retro
    FROM v_player_crosswalk
    WHERE key_mlbam IS NOT NULL
    GROUP BY key_mlbam
)
SELECT p.player_mlbam
FROM sc_players p
LEFT JOIN retro_map rm ON p.player_mlbam = rm.key_mlbam
WHERE rm.key_retro IS NULL
ORDER BY p.player_mlbam;
"""


def check_join_coverage(con: duckdb.DuckDBPyConnection, season: int) -> dict[str, Any]:
    """Execute join coverage queries for a given season and return metric dictionary."""
    # (a) Games coverage
    g_row = con.execute(GAMES_COVERAGE_QUERY, [season, season, season]).fetchone()
    games_sc = int(g_row[0]) if g_row and g_row[0] is not None else 0
    games_retro = int(g_row[1]) if g_row and g_row[1] is not None else 0
    games_joined = int(g_row[2]) if g_row and g_row[2] is not None else 0

    # (b) Plate appearances coverage
    pa_row = con.execute(PA_COVERAGE_QUERY, [season] * 5).fetchone()
    pa_sc = int(pa_row[0]) if pa_row and pa_row[0] is not None else 0
    pa_retro = int(pa_row[1]) if pa_row and pa_row[1] is not None else 0
    total_joined = int(pa_row[2]) if pa_row and pa_row[2] is not None else 0
    equal_pa_games = int(pa_row[3]) if pa_row and pa_row[3] is not None else 0

    # (c) Plate appearance agreement in equal-PA games
    agree_row = con.execute(PA_AGREEMENT_QUERY, [season] * 7).fetchone()
    total_equal_pa = int(agree_row[0]) if agree_row and agree_row[0] is not None else 0
    bat_matches = int(agree_row[1]) if agree_row and agree_row[1] is not None else 0
    pit_matches = int(agree_row[2]) if agree_row and agree_row[2] is not None else 0
    bat_rate = float(agree_row[3]) if agree_row and agree_row[3] is not None else 0.0
    pit_rate = float(agree_row[4]) if agree_row and agree_row[4] is not None else 0.0

    # (d) Unmapped players
    p_row = con.execute(UNMAPPED_PLAYERS_QUERY, [season, season]).fetchone()
    total_players = int(p_row[0]) if p_row and p_row[0] is not None else 0
    unmapped_count = int(p_row[1]) if p_row and p_row[1] is not None else 0

    unmapped_ids: list[int] = []
    if unmapped_count > 0:
        id_rows = con.execute(UNMAPPED_PLAYER_IDS_QUERY, [season, season]).fetchall()
        unmapped_ids = [int(r[0]) for r in id_rows if r[0] is not None]

    equal_pa_pct = round(equal_pa_games * 100.0 / total_joined, 2) if total_joined > 0 else 0.0

    return {
        "season": season,
        "games": {
            "statcast": games_sc,
            "retrosheet": games_retro,
            "joined": games_joined,
        },
        "plate_appearances": {
            "statcast": pa_sc,
            "retrosheet": pa_retro,
            "joined_games": total_joined,
            "equal_pa_games": equal_pa_games,
            "equal_pa_pct": equal_pa_pct,
        },
        "pa_agreement": {
            "total_equal_game_pa": total_equal_pa,
            "batter_matches": bat_matches,
            "pitcher_matches": pit_matches,
            "batter_agreement_rate": bat_rate,
            "pitcher_agreement_rate": pit_rate,
        },
        "players": {
            "total_statcast_players": total_players,
            "unmapped_players": unmapped_count,
            "unmapped_player_ids": unmapped_ids,
        },
    }


def format_text_report(reports: list[dict[str, Any]]) -> str:
    """Format join coverage metrics into human-readable plain text tables."""
    lines: list[str] = []
    for r in reports:
        season = r["season"]
        g = r["games"]
        pa = r["plate_appearances"]
        ag = r["pa_agreement"]
        pl = r["players"]

        lines.append("=" * 60)
        lines.append(f"Join Coverage Report: Season {season}")
        lines.append("=" * 60)
        lines.append("  Games:")
        lines.append(f"    Statcast games:           {g['statcast']:>8,}")
        lines.append(f"    Retrosheet games:         {g['retrosheet']:>8,}")
        lines.append(f"    Joined by crosswalk:      {g['joined']:>8,}")
        lines.append("  Plate Appearances (Joined Games):")
        lines.append(f"    Statcast PAs:             {pa['statcast']:>8,}")
        lines.append(f"    Retrosheet PAs (BAT_FL):  {pa['retrosheet']:>8,}")
        lines.append(
            f"    Games with equal PAs:     {pa['equal_pa_games']:>8,} / {pa['joined_games']:,} ({pa['equal_pa_pct']:.1f}%)"
        )
        lines.append("  PA Identity Agreement (Equal-PA Games):")
        lines.append(f"    Paired PAs checked:       {ag['total_equal_game_pa']:>8,}")
        lines.append(
            f"    Batter agreement:         {ag['batter_matches']:>8,} ({ag['batter_agreement_rate'] * 100:.2f}%)"
        )
        lines.append(
            f"    Pitcher agreement:        {ag['pitcher_matches']:>8,} ({ag['pitcher_agreement_rate'] * 100:.2f}%)"
        )
        lines.append("  Players (Statcast):")
        lines.append(f"    Distinct players:         {pl['total_statcast_players']:>8,}")
        lines.append(f"    Missing key_retro:        {pl['unmapped_players']:>8,}")
        if pl["unmapped_player_ids"]:
            ids_str = ", ".join(str(i) for i in pl["unmapped_player_ids"][:10])
            if len(pl["unmapped_player_ids"]) > 10:
                ids_str += f", ... ({len(pl['unmapped_player_ids'])} total)"
            lines.append(f"    Unmapped MLBAM IDs:       {ids_str}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    """CLI entrypoint for join coverage reporting."""
    parser = argparse.ArgumentParser(
        description="Verify cross-source join coverage across Statcast, Retrosheet, and Chadwick."
    )
    parser.add_argument(
        "--season",
        "-s",
        type=int,
        action="append",
        dest="seasons",
        help="Season year to evaluate (repeatable; default: 2015, 2019, 2023).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print coverage metrics as JSON.",
    )
    args = parser.parse_args()
    seasons = sorted(set(args.seasons)) if args.seasons else [2015, 2019, 2023]

    try:
        con = connect_db(read_only=True)
    except Exception as exc:
        msg = (
            f"Failed to open read-only database: {exc}\n"
            "Ensure views are synced via `baseballpy db sync`."
        )
        if args.json:
            print(json.dumps({"error": msg}))
        else:
            print(msg, file=sys.stderr)
        return 0

    reports: list[dict[str, Any]] = []
    try:
        for season in seasons:
            reports.append(check_join_coverage(con, season))
    finally:
        con.close()

    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        print(format_text_report(reports))

    return 0


if __name__ == "__main__":
    sys.exit(main())
