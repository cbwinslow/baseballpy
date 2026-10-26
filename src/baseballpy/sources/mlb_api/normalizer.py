"""Normalizer transforming MLB Stats API responses into strongly-typed PyArrow Tables."""

from datetime import datetime
from typing import Any

import pyarrow as pa

from baseballpy.sources.mlb_api.schemas import (
    MLB_BOX_BATTING_SCHEMA,
    MLB_BOX_PITCHING_SCHEMA,
    MLB_DRAFT_SCHEMA,
    MLB_LIVE_PLAYS_SCHEMA,
    MLB_ROSTERS_SCHEMA,
    MLB_SCHEDULE_SCHEMA,
    MLB_STANDINGS_SCHEMA,
    MLB_TEAMS_SCHEMA,
    MLB_TRANSACTIONS_SCHEMA,
    MLB_VENUES_SCHEMA,
)


def _safe_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> int | None:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


class MlbApiNormalizer:
    """Transforms deserialized MLB Stats API objects into strongly-typed PyArrow Tables."""

    def normalize_schedule(self, data: dict[str, Any]) -> pa.Table:
        """Normalize /v1/schedule response."""
        dates = data.get("dates", [])
        records: list[dict[str, Any]] = []

        for d in dates:
            date_str = d.get("date", "")
            try:
                game_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                game_date = None

            for g in d.get("games", []):
                teams = g.get("teams", {})
                away = teams.get("away", {})
                home = teams.get("home", {})
                venue = g.get("venue", {})
                status = g.get("status", {})

                records.append(
                    {
                        "game_pk": g.get("gamePk"),
                        "game_date": game_date,
                        "game_type": g.get("gameType", "R"),
                        "season": _safe_int(g.get("season")),
                        "status_code": status.get("statusCode", ""),
                        "status_detailed": status.get("detailedState", ""),
                        "away_team_id": away.get("team", {}).get("id"),
                        "away_team_name": away.get("team", {}).get("name", ""),
                        "away_score": _safe_int(away.get("score")),
                        "home_team_id": home.get("team", {}).get("id"),
                        "home_team_name": home.get("team", {}).get("name", ""),
                        "home_score": _safe_int(home.get("score")),
                        "doubleheader": g.get("doubleHeader", "N"),
                        "game_num": _safe_int(g.get("gameNumber", 1)),
                        "venue_id": venue.get("id"),
                        "venue_name": venue.get("name", ""),
                    }
                )

        if not records:
            return pa.Table.from_batches([], schema=MLB_SCHEDULE_SCHEMA)

        arrays = []
        for field in MLB_SCHEDULE_SCHEMA:
            col_name = field.name
            target_type = field.type
            col_vals = [r.get(col_name) for r in records]
            arrays.append(pa.array(col_vals, type=target_type))

        return pa.Table.from_arrays(arrays, schema=MLB_SCHEDULE_SCHEMA)

    def normalize_live_plays(self, events: list[dict[str, Any]]) -> pa.Table:
        """Normalize discrete live play events into PyArrow Table."""
        if not events:
            return pa.Table.from_batches([], schema=MLB_LIVE_PLAYS_SCHEMA)

        arrays = []
        for field in MLB_LIVE_PLAYS_SCHEMA:
            col_name = field.name
            target_type = field.type
            col_vals = [e.get(col_name) for e in events]
            arrays.append(pa.array(col_vals, type=target_type))

        return pa.Table.from_arrays(arrays, schema=MLB_LIVE_PLAYS_SCHEMA)

    def normalize_boxscore(
        self, data: dict[str, Any], game_pk: int
    ) -> tuple[pa.Table, pa.Table]:
        """Normalize /v1/game/{game_pk}/boxscore into (batting_table, pitching_table)."""
        teams = data.get("teams", {})
        batting_records: list[dict[str, Any]] = []
        pitching_records: list[dict[str, Any]] = []

        for side in ("away", "home"):
            team_info = teams.get(side, {})
            team_id = team_info.get("team", {}).get("id", 0)
            players = team_info.get("players", {})

            for _, p_data in players.items():
                person = p_data.get("person", {})
                player_id = person.get("id", 0)
                player_name = person.get("fullName", "")
                position = p_data.get("position", {}).get("abbreviation", "")
                batting_order = _safe_int(p_data.get("battingOrder"))

                stats = p_data.get("stats", {})
                batting = stats.get("batting", {})
                pitching = stats.get("pitching", {})

                # If player batted
                if batting and batting.get("atBats") is not None:
                    batting_records.append(
                        {
                            "game_pk": game_pk,
                            "team_id": team_id,
                            "player_id": player_id,
                            "player_name": player_name,
                            "position": position,
                            "batting_order": batting_order,
                            "ab": _safe_int(batting.get("atBats")),
                            "r": _safe_int(batting.get("runs")),
                            "h": _safe_int(batting.get("hits")),
                            "d": _safe_int(batting.get("doubles")),
                            "t": _safe_int(batting.get("triples")),
                            "hr": _safe_int(batting.get("homeRuns")),
                            "rbi": _safe_int(batting.get("rbi")),
                            "bb": _safe_int(batting.get("baseOnBalls")),
                            "so": _safe_int(batting.get("strikeOuts")),
                            "sb": _safe_int(batting.get("stolenBases")),
                            "cs": _safe_int(batting.get("caughtStealing")),
                        }
                    )

                # If player pitched
                if pitching and pitching.get("inningsPitched") is not None:
                    pitching_records.append(
                        {
                            "game_pk": game_pk,
                            "team_id": team_id,
                            "player_id": player_id,
                            "player_name": player_name,
                            "ip": _safe_float(pitching.get("inningsPitched")),
                            "h": _safe_int(pitching.get("hits")),
                            "r": _safe_int(pitching.get("runs")),
                            "er": _safe_int(pitching.get("earnedRuns")),
                            "bb": _safe_int(pitching.get("baseOnBalls")),
                            "so": _safe_int(pitching.get("strikeOuts")),
                            "hr": _safe_int(pitching.get("homeRuns")),
                            "pitches": _safe_int(pitching.get("pitchesThrown")),
                            "strikes": _safe_int(pitching.get("strikes")),
                        }
                    )

        def _to_table(recs: list[dict[str, Any]], schema: pa.Schema) -> pa.Table:
            if not recs:
                return pa.Table.from_batches([], schema=schema)
            arrs = [pa.array([r.get(f.name) for r in recs], type=f.type) for f in schema]
            return pa.Table.from_arrays(arrs, schema=schema)

        return (
            _to_table(batting_records, MLB_BOX_BATTING_SCHEMA),
            _to_table(pitching_records, MLB_BOX_PITCHING_SCHEMA),
        )

    def normalize_standings(self, data: dict[str, Any], season: int) -> pa.Table:
        """Normalize /v1/standings response."""
        records: list[dict[str, Any]] = []
        for record in data.get("records", []):
            division = record.get("division", {})
            div_id = division.get("id", 0)
            div_name = division.get("name", "")

            for tr in record.get("teamRecords", []):
                streak = tr.get("streak", {}).get("streakCode", "")
                records.append(
                    {
                        "season": season,
                        "division_id": div_id,
                        "division_name": div_name,
                        "team_id": tr.get("team", {}).get("id", 0),
                        "team_name": tr.get("team", {}).get("name", ""),
                        "wins": _safe_int(tr.get("wins")),
                        "losses": _safe_int(tr.get("losses")),
                        "win_pct": _safe_float(tr.get("winningPercentage")),
                        "games_back": _safe_float(tr.get("gamesBack")),
                        "wild_card_gb": _safe_float(tr.get("wildCardGamesBack")),
                        "run_differential": _safe_int(tr.get("runDifferential")),
                        "streak": streak,
                        "elim_num": _safe_int(tr.get("eliminationNumber")),
                    }
                )

        if not records:
            return pa.Table.from_batches([], schema=MLB_STANDINGS_SCHEMA)

        arrays = [pa.array([r.get(f.name) for r in records], type=f.type) for f in MLB_STANDINGS_SCHEMA]
        return pa.Table.from_arrays(arrays, schema=MLB_STANDINGS_SCHEMA)

    def normalize_teams(self, data: dict[str, Any]) -> pa.Table:
        """Normalize /v1/teams response."""
        records: list[dict[str, Any]] = []
        for t in data.get("teams", []):
            league = t.get("league", {})
            division = t.get("division", {})
            venue = t.get("venue", {})

            records.append(
                {
                    "team_id": t.get("id", 0),
                    "team_name": t.get("name", ""),
                    "abbreviation": t.get("abbreviation", ""),
                    "league_id": league.get("id", 0),
                    "league_name": league.get("name", ""),
                    "division_id": division.get("id", 0),
                    "division_name": division.get("name", ""),
                    "venue_id": venue.get("id", 0),
                    "venue_name": venue.get("name", ""),
                    "active": bool(t.get("active", True)),
                }
            )

        if not records:
            return pa.Table.from_batches([], schema=MLB_TEAMS_SCHEMA)

        arrays = [pa.array([r.get(f.name) for r in records], type=f.type) for f in MLB_TEAMS_SCHEMA]
        return pa.Table.from_arrays(arrays, schema=MLB_TEAMS_SCHEMA)

    def normalize_roster(self, data: dict[str, Any], team_id: int) -> pa.Table:
        """Normalize /v1/teams/{team_id}/roster response."""
        records: list[dict[str, Any]] = []
        for r in data.get("roster", []):
            person = r.get("person", {})
            pos = r.get("position", {})
            status = r.get("status", {}).get("description", "Active")

            records.append(
                {
                    "team_id": team_id,
                    "player_id": person.get("id", 0),
                    "player_name": person.get("fullName", ""),
                    "jersey_number": r.get("jerseyNumber", ""),
                    "position_code": pos.get("abbreviation", ""),
                    "position_name": pos.get("name", ""),
                    "status": status,
                }
            )

        if not records:
            return pa.Table.from_batches([], schema=MLB_ROSTERS_SCHEMA)

        arrays = [pa.array([r.get(f.name) for r in records], type=f.type) for f in MLB_ROSTERS_SCHEMA]
        return pa.Table.from_arrays(arrays, schema=MLB_ROSTERS_SCHEMA)

    def normalize_transactions(self, data: dict[str, Any]) -> pa.Table:
        """Normalize /v1/transactions response."""
        records: list[dict[str, Any]] = []
        for t in data.get("transactions", []):
            person = t.get("person", {})
            from_team = t.get("fromTeam", {})
            to_team = t.get("toTeam", {})

            records.append(
                {
                    "transaction_id": _safe_int(t.get("id")),
                    "date": t.get("date", ""),
                    "player_id": person.get("id", 0),
                    "player_name": person.get("fullName", ""),
                    "from_team_id": from_team.get("id", 0),
                    "to_team_id": to_team.get("id", 0),
                    "type_code": t.get("typeCode", ""),
                    "type_desc": t.get("typeDesc", ""),
                    "description": t.get("description", ""),
                }
            )

        if not records:
            return pa.Table.from_batches([], schema=MLB_TRANSACTIONS_SCHEMA)

        arrays = [pa.array([r.get(f.name) for r in records], type=f.type) for f in MLB_TRANSACTIONS_SCHEMA]
        return pa.Table.from_arrays(arrays, schema=MLB_TRANSACTIONS_SCHEMA)

    def normalize_draft(self, data: dict[str, Any], year: int) -> pa.Table:
        """Normalize /v1/draft response."""
        records: list[dict[str, Any]] = []
        for d in data.get("drafts", {}).get("rounds", []):
            round_str = str(d.get("round", ""))
            for p in d.get("picks", []):
                person = p.get("person", {})
                team = p.get("team", {})
                school = p.get("school", {})

                records.append(
                    {
                        "year": year,
                        "round": round_str,
                        "pick_round": _safe_int(p.get("pickRound")),
                        "pick_overall": _safe_int(p.get("pickOverall")),
                        "team_id": team.get("id", 0),
                        "player_id": person.get("id", 0),
                        "player_name": person.get("fullName", ""),
                        "school_name": school.get("name", ""),
                        "signing_bonus": _safe_int(p.get("signingBonus")),
                    }
                )

        if not records:
            return pa.Table.from_batches([], schema=MLB_DRAFT_SCHEMA)

        arrays = [pa.array([r.get(f.name) for r in records], type=f.type) for f in MLB_DRAFT_SCHEMA]
        return pa.Table.from_arrays(arrays, schema=MLB_DRAFT_SCHEMA)

    def normalize_venues(self, data: dict[str, Any]) -> pa.Table:
        """Normalize /v1/venues response."""
        records: list[dict[str, Any]] = []
        for v in data.get("venues", []):
            loc = v.get("location", {})
            turf = v.get("fieldInfo", {}).get("turfType", "")
            roof = v.get("fieldInfo", {}).get("roofType", "")

            records.append(
                {
                    "venue_id": v.get("id", 0),
                    "venue_name": v.get("name", ""),
                    "city": loc.get("city", ""),
                    "state": loc.get("state", ""),
                    "country": loc.get("country", ""),
                    "capacity": _safe_int(v.get("fieldInfo", {}).get("capacity")),
                    "turf_type": turf,
                    "roof_type": roof,
                }
            )

        if not records:
            return pa.Table.from_batches([], schema=MLB_VENUES_SCHEMA)

        arrays = [pa.array([r.get(f.name) for r in records], type=f.type) for f in MLB_VENUES_SCHEMA]
        return pa.Table.from_arrays(arrays, schema=MLB_VENUES_SCHEMA)
