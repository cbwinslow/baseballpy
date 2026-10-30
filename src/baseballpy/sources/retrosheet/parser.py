"""Retrosheet parsers bridging chadwickpy into strongly-typed PyArrow Tables."""

import csv
import io
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow as pa

from baseballpy.core.coerce import NULL_TOKENS, CoercionError, to_bool, to_int
from baseballpy.core.quarantine import Quarantine, collect_bad_values, record_bad_value, safe_array
from baseballpy.core.schema_tools import EXTRAS, normalize_csv
from baseballpy.sources.retrosheet import _chadwick_adapter as cw
from baseballpy.sources.retrosheet.schema import (
    RETROSHEET_BOX_BATTING_SCHEMA,
    RETROSHEET_BOX_PITCHING_SCHEMA,
    RETROSHEET_DAILY_SPLITS_SCHEMA,
    RETROSHEET_EVENT_SCHEMA,
    RETROSHEET_FLAT_SCHEMAS,
    RETROSHEET_GAMELOG_SCHEMA,
    RETROSHEET_ROSTER_SCHEMA,
    RETROSHEET_SUBSTITUTIONS_SCHEMA,
)
from baseballpy.sources.retrosheet.tables import RETROSHEET_DEFAULT_HEADERS

logger = logging.getLogger(__name__)


def _arr(values: list[Any], field: pa.Field) -> pa.Array:
    return safe_array(values, field.type, source="retrosheet", dataset="parse", column=field.name)


def _safe_int(val: Any) -> int | None:
    """Coerce to int; unparseable values become NULL *and* are quarantined by the parser."""
    try:
        return to_int(val, nulls=NULL_TOKENS)
    except CoercionError as exc:
        record_bad_value("int", val, exc)
        return None


def _safe_bool(val: Any) -> bool | None:
    """Coerce to bool; unparseable values become NULL *and* are quarantined by the parser."""
    try:
        return to_bool(val, nulls=NULL_TOKENS)
    except CoercionError as exc:
        record_bad_value("bool", val, exc)
        return None


def _load_league(paths: list[Path], year: int | None = None) -> cw.League | None:
    """Load the season TEAM file for name resolution; failures are logged, not hidden."""
    if not paths:
        return None
    parent = paths[0].parent
    team_file = parent / f"TEAM{year}" if year else None
    if team_file and team_file.exists():
        try:
            league = cw.League()
            league.read(team_file.read_bytes())
            return league
        except (ValueError, KeyError, IndexError, UnicodeDecodeError, OSError):
            logger.warning(
                "could not load Retrosheet team file %s; player/team names will be unresolved",
                team_file,
                exc_info=True,
            )
    return None


def _chain_head(node: Any) -> Any:
    """First element of chadwickpy's doubly linked box chains.

    ``box.slots[slot][team]`` and ``box.pitchers[team]`` point at the *most recent* player; the
    starter (and every substitute before the last) is reached through ``prev``. Walking only
    ``next`` from the handle silently drops everyone but the last entry.
    """
    while node is not None and getattr(node, "prev", None) is not None:
        node = node.prev
    return node


class RetrosheetEventParser:
    """Parses Retrosheet .EVA / .EVN / .EVE event files using pure-Python chadwickpy."""

    def __init__(self, league: cw.League | None = None) -> None:
        self.league = league

    @collect_bad_values("retrosheet", "events")
    def parse_files(self, paths: list[Path], year: int | None = None) -> pa.Table:
        """Parse multiple event files into a consolidated typed PyArrow Table."""
        if not paths:
            return pa.Table.from_batches([], schema=RETROSHEET_EVENT_SCHEMA)

        league = self.league or _load_league(paths, year)

        rows: list[dict[str, str]] = []
        for path in paths:
            rows.extend(cw.event_rows(path.read_bytes(), league=league))
        if not rows:
            return pa.Table.from_batches([], schema=RETROSHEET_EVENT_SCHEMA)

        known = set(RETROSHEET_EVENT_SCHEMA.names)
        arrays = []
        for field in RETROSHEET_EVENT_SCHEMA:
            if field.name == EXTRAS:
                continue
            values: list[Any] = [row.get(field.name) for row in rows]
            if field.type == pa.bool_():
                values = [_safe_bool(v) for v in values]
            elif pa.types.is_integer(field.type):
                values = [_safe_int(v) for v in values]
            arrays.append(_arr(values, field))
        arrays.append(_event_extras(rows, known))
        return pa.Table.from_arrays(arrays, schema=RETROSHEET_EVENT_SCHEMA)


def _event_extras(rows: list[dict[str, str]], known: set[str]) -> pa.Array:
    """JSON text of the fields chadwickpy returned that the schema has no column for (else NULL)."""
    unknown = sorted({key for row in rows for key in row if key not in known})
    if not unknown:
        return pa.nulls(len(rows), type=pa.string())
    logger.warning(
        "retrosheet events: chadwickpy returned unknown field(s) %s (kept in _extras)", unknown
    )
    payload = [json.dumps({k: row[k] for k in unknown if k in row}) for row in rows]
    return pa.array(payload, pa.string())


class RetrosheetBoxScoreParser:
    """Parses game boxscores into Batting and Pitching PyArrow Tables via cwbox."""

    def __init__(self, league: cw.League | None = None) -> None:
        self.league = league

    @collect_bad_values("retrosheet", "boxscores")
    def parse_files(self, paths: list[Path], year: int | None = None) -> tuple[pa.Table, pa.Table]:
        """Parse event files and return (batting_table, pitching_table)."""
        if not paths:
            return (
                pa.Table.from_batches([], schema=RETROSHEET_BOX_BATTING_SCHEMA),
                pa.Table.from_batches([], schema=RETROSHEET_BOX_PITCHING_SCHEMA),
            )

        league = self.league or _load_league(paths, year)

        batting_records: list[dict[str, Any]] = []
        pitching_records: list[dict[str, Any]] = []

        for path in paths:
            data = path.read_bytes()
            for game, _, _ in cw.iterate_games(data, league=league):
                game_id = game.game_id or ""
                vis_team = game.info_lookup("visteam") or ""
                home_team = game.info_lookup("hometeam") or ""
                box = cw.box_create(game)

                # 1. Batting lines from slots
                for team_idx, team_code in enumerate((vis_team, home_team)):
                    for slot_idx in range(len(box.slots)):
                        # chadwick keeps the *latest* occupant of a slot; rewind to the starter
                        player = _chain_head(box.slots[slot_idx][team_idx])
                        while player is not None:
                            b = player.batting
                            pos = player.positions[0] if player.positions else player.start_position
                            batting_records.append(
                                {
                                    "game_id": game_id,
                                    "team_id": team_code,
                                    "player_id": player.player_id,
                                    "player_name": player.name,
                                    "slot": slot_idx,
                                    "pos": pos,
                                    "ab": b.ab,
                                    "r": b.r,
                                    "h": b.h,
                                    "d": b.b2,
                                    "t": b.b3,
                                    "hr": b.hr,
                                    "rbi": b.bi,
                                    "bb": b.bb,
                                    "ibb": b.ibb,
                                    "so": b.so,
                                    "hbp": b.hp,
                                    "sh": b.sh,
                                    "sf": b.sf,
                                    "sb": b.sb,
                                    "cs": b.cs,
                                    "gidp": b.gdp,
                                    "pa": b.pa,
                                }
                            )
                            player = player.next

                # 2. Pitching lines
                for team_idx, team_code in enumerate((vis_team, home_team)):
                    pitcher = _chain_head(box.pitchers[team_idx])  # starter first
                    seq = 1
                    while pitcher is not None:
                        p = pitcher.pitching
                        pitching_records.append(
                            {
                                "game_id": game_id,
                                "team_id": team_code,
                                "pitcher_id": pitcher.player_id,
                                "pitcher_name": pitcher.name,
                                "starter_fl": (seq == 1),
                                "seq": seq,
                                "outs_recorded": p.outs,
                                "bf": p.bf,
                                "h": p.h,
                                "r": p.r,
                                "er": p.er,
                                "bb": p.bb,
                                "ibb": p.ibb,
                                "so": p.so,
                                "hr": p.hr,
                                "hbp": p.hb,
                                "wp": p.wp,
                                "bk": p.bk,
                                "pitches": p.pitches if p.pitches > 0 else None,
                                "strikes": p.strikes if p.strikes > 0 else None,
                                "w": bool(p.w),
                                "l": bool(p.l),
                                "sv": bool(p.sv),
                                "cg": bool(p.cg),
                                "sho": bool(p.sho),
                                "gf": bool(p.gf),
                            }
                        )
                        seq += 1
                        pitcher = pitcher.next

        # Build Arrow tables
        def _build_table(records: list[dict[str, Any]], schema: pa.Schema) -> pa.Table:
            if not records:
                return pa.Table.from_batches([], schema=schema)
            arrays = []
            for field in schema:
                name = field.name
                col_vals = [r.get(name) for r in records]
                arrays.append(_arr(col_vals, field))
            return pa.Table.from_arrays(arrays, schema=schema)

        return (
            _build_table(batting_records, RETROSHEET_BOX_BATTING_SCHEMA),
            _build_table(pitching_records, RETROSHEET_BOX_PITCHING_SCHEMA),
        )


class RetrosheetDailySplitsParser:
    """Parses daily player appearance records via chadwickpy daily."""

    def __init__(self, league: cw.League | None = None) -> None:
        self.league = league

    @collect_bad_values("retrosheet", "daily_splits")
    def parse_files(self, paths: list[Path], year: int | None = None) -> pa.Table:
        """Parse daily lines from event files."""
        if not paths:
            return pa.Table.from_batches([], schema=RETROSHEET_DAILY_SPLITS_SCHEMA)

        league = self.league or _load_league(paths, year)
        records: list[dict[str, Any]] = []

        for path in paths:
            data = path.read_bytes()
            for line in cw.daily.daily_lines(data, league=league):
                row = next(csv.reader([line]))
                rec: dict[str, Any] = {}
                for idx, field in enumerate(RETROSHEET_DAILY_SPLITS_SCHEMA):
                    name = field.name
                    target_type = field.type
                    val = row[idx] if idx < len(row) else None

                    if pa.types.is_integer(target_type):
                        rec[name] = _safe_int(val)
                    else:
                        rec[name] = val if val else None
                records.append(rec)

        if not records:
            return pa.Table.from_batches([], schema=RETROSHEET_DAILY_SPLITS_SCHEMA)

        arrays = []
        for field in RETROSHEET_DAILY_SPLITS_SCHEMA:
            name = field.name
            target_type = field.type
            col_vals = [r.get(name) for r in records]
            arrays.append(_arr(col_vals, field))

        return pa.Table.from_arrays(arrays, schema=RETROSHEET_DAILY_SPLITS_SCHEMA)


class RetrosheetSubstitutionsParser:
    """Parses in-game player substitutions via chadwickpy sub."""

    def __init__(self, league: cw.League | None = None) -> None:
        self.league = league

    @collect_bad_values("retrosheet", "substitutions")
    def parse_files(self, paths: list[Path], year: int | None = None) -> pa.Table:
        """Parse substitutions from event files."""
        if not paths:
            return pa.Table.from_batches([], schema=RETROSHEET_SUBSTITUTIONS_SCHEMA)

        league = self.league or _load_league(paths, year)
        records: list[dict[str, Any]] = []

        for path in paths:
            data = path.read_bytes()
            for line in cw.sub.sub_lines(data, league=league):
                row = next(csv.reader([line]))
                rec: dict[str, Any] = {}
                for idx, field in enumerate(RETROSHEET_SUBSTITUTIONS_SCHEMA):
                    name = field.name
                    target_type = field.type
                    val = row[idx] if idx < len(row) else None

                    if pa.types.is_integer(target_type):
                        rec[name] = _safe_int(val)
                    else:
                        rec[name] = val if val else None
                records.append(rec)

        if not records:
            return pa.Table.from_batches([], schema=RETROSHEET_SUBSTITUTIONS_SCHEMA)

        arrays = []
        for field in RETROSHEET_SUBSTITUTIONS_SCHEMA:
            name = field.name
            target_type = field.type
            col_vals = [r.get(name) for r in records]
            arrays.append(_arr(col_vals, field))

        return pa.Table.from_arrays(arrays, schema=RETROSHEET_SUBSTITUTIONS_SCHEMA)


class RetrosheetGameLogParser:
    """Parses 161-column Retrosheet Game Logs (glYYYY.txt) into strongly-typed PyArrow Tables."""

    @collect_bad_values("retrosheet", "gamelogs")
    def parse_file(self, path: Path) -> pa.Table:
        """Parse a game log file into PyArrow Table."""
        if not path.exists():
            return pa.Table.from_batches([], schema=RETROSHEET_GAMELOG_SCHEMA)

        text = path.read_text(encoding="utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text, newline=""))
        standard_fields = [f for f in RETROSHEET_GAMELOG_SCHEMA if f.name != "_extras"]

        records: list[dict[str, Any]] = []
        for row in reader:
            if not row or (len(row) == 1 and not row[0].strip()):
                continue
            if len(row) < 10:
                record_bad_value(
                    "row",
                    ",".join(row),
                    f"game log row has {len(row)} fields, expected at least 10",
                )
                continue
            rec: dict[str, Any] = {}
            for i, field in enumerate(standard_fields):
                val = row[i] if i < len(row) else None
                name = field.name
                target_type = field.type

                if target_type == pa.date32():
                    if val and len(val) == 8 and val.isdigit():
                        rec[name] = datetime.strptime(val, "%Y%m%d").date()
                    else:
                        rec[name] = None
                elif pa.types.is_integer(target_type):
                    rec[name] = _safe_int(val)
                elif target_type == pa.bool_():
                    rec[name] = _safe_bool(val)
                else:
                    rec[name] = val if val else None

            if len(row) > len(standard_fields):
                extras = {
                    f"field_{idx + 1}": row[idx] for idx in range(len(standard_fields), len(row))
                }
                rec["_extras"] = json.dumps(extras)
            else:
                rec["_extras"] = None

            records.append(rec)

        if not records:
            return pa.Table.from_batches([], schema=RETROSHEET_GAMELOG_SCHEMA)

        arrays = []
        for field in RETROSHEET_GAMELOG_SCHEMA:
            name = field.name
            target_type = field.type
            col_vals = [r.get(name) for r in records]
            arrays.append(_arr(col_vals, field))

        return pa.Table.from_arrays(arrays, schema=RETROSHEET_GAMELOG_SCHEMA)


class RetrosheetRosterParser:
    """Parses Retrosheet roster files (.ROS) into PyArrow Tables."""

    @collect_bad_values("retrosheet", "rosters")
    def parse_files(self, paths: list[Path], year: int | None = None) -> pa.Table:
        """Parse one or more .ROS roster files."""
        records: list[dict[str, Any]] = []

        for path in paths:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 6:
                    record_bad_value(
                        "row",
                        line,
                        f"roster row has {len(parts)} fields, expected at least 6",
                    )
                    continue

                if len(parts) > 7:
                    extras = {f"field_{idx + 1}": parts[idx] for idx in range(7, len(parts))}
                    extras_val: str | None = json.dumps(extras)
                else:
                    extras_val = None

                records.append(
                    {
                        "player_id": parts[0],
                        "last_name": parts[1],
                        "first_name": parts[2],
                        "bats": parts[3],
                        "throws": parts[4],
                        "team": parts[5],
                        "position": parts[6] if len(parts) > 6 else "",
                        "year": year,
                        "_extras": extras_val,
                    }
                )

        if not records:
            return pa.Table.from_batches([], schema=RETROSHEET_ROSTER_SCHEMA)

        arrays = []
        for field in RETROSHEET_ROSTER_SCHEMA:
            name = field.name
            col_vals = [r.get(name) for r in records]
            arrays.append(_arr(col_vals, field))

        return pa.Table.from_arrays(arrays, schema=RETROSHEET_ROSTER_SCHEMA)


class RetrosheetFlatParser:
    """Header-based parser for flat Retrosheet files: ``reference/*.csv``, schedules, umpires and
    discrepancy files.

    Columns are matched by upstream header name against the generated strict schema (so column
    order and added columns never corrupt data), dates are parsed with the format observed in the
    real files, unknown columns are kept in ``_extras`` and files that ship without a header row
    (a few old schedules) get the documented default header.
    """

    def __init__(self, quarantine: Quarantine | None = None) -> None:
        self._quarantine = quarantine

    def parse_bytes(self, dataset: str, raw: bytes | str) -> pa.Table:
        """Parse one file's bytes for a flat dataset (e.g. ``schedule``, ``reference_teams``)."""
        try:
            schema = RETROSHEET_FLAT_SCHEMAS[dataset]
        except KeyError:
            raise ValueError(
                f"Unknown flat Retrosheet dataset '{dataset}'. Valid: {sorted(RETROSHEET_FLAT_SCHEMAS)}"
            ) from None
        data = raw.encode("utf-8") if isinstance(raw, str) else raw
        header: list[str] | None = None
        default = RETROSHEET_DEFAULT_HEADERS.get(dataset)
        if default is not None:
            first = data.split(b"\n", 1)[0].decode("utf-8-sig", errors="replace")
            if re.match(r'^"?\d{8}"?,', first.strip()):
                logger.info(
                    "%s file has no header row; using the documented default header", dataset
                )
                header = default.split(",")
        return normalize_csv(
            data,
            schema,
            source="retrosheet",
            dataset=dataset,
            quarantine=self._quarantine,
            header=header,
        )

    def parse_path(self, dataset: str, path: Path) -> pa.Table:
        """Parse a flat file from disk."""
        return self.parse_bytes(dataset, path.read_bytes())


class RetrosheetReferenceParser(RetrosheetFlatParser):
    """Parses ``reference/*.csv`` tables (ballparks, teams, ejections, coaches, relatives, biofile)."""

    def parse_file(self, table_name: str, path: Path) -> pa.Table:
        """Parse a reference CSV into a PyArrow Table by header name."""
        dataset = f"reference_{table_name.lower()}"
        if dataset not in RETROSHEET_FLAT_SCHEMAS:
            known = sorted(
                k.removeprefix("reference_")
                for k in RETROSHEET_FLAT_SCHEMAS
                if k.startswith("reference_")
            )
            raise ValueError(f"Unknown reference schema '{table_name}'. Valid schemas: {known}")
        return self.parse_path(dataset, path)
