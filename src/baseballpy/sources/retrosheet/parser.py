"""Retrosheet parsers bridging chadwickpy into strongly-typed PyArrow Tables."""

import csv
import functools
import io
import logging
from collections.abc import Callable
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

import pyarrow as pa
from chadwickpy.box import box_create
from chadwickpy.roster import League
from chadwickpy.tools import daily, sub
from chadwickpy.tools.events import event_rows
from chadwickpy.tools.tools import iterate_games

from baseballpy.core.coerce import NULL_TOKENS, CoercionError, to_bool, to_int
from baseballpy.core.quarantine import get_quarantine
from baseballpy.sources.retrosheet.schema import (
    RETROSHEET_BALLPARKS_SCHEMA,
    RETROSHEET_BIOFILE_SCHEMA,
    RETROSHEET_BOX_BATTING_SCHEMA,
    RETROSHEET_BOX_PITCHING_SCHEMA,
    RETROSHEET_COACHES_SCHEMA,
    RETROSHEET_DAILY_SPLITS_SCHEMA,
    RETROSHEET_EJECTIONS_SCHEMA,
    RETROSHEET_EVENT_SCHEMA,
    RETROSHEET_GAMELOG_SCHEMA,
    RETROSHEET_RELATIVES_SCHEMA,
    RETROSHEET_ROSTER_SCHEMA,
    RETROSHEET_SUBSTITUTIONS_SCHEMA,
    RETROSHEET_TEAMS_SCHEMA,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")
_BAD_VALUES: ContextVar[list[dict[str, Any]] | None] = ContextVar("retrosheet_bad", default=None)


def _record_bad(kind: str, val: Any, exc: CoercionError) -> None:
    bucket = _BAD_VALUES.get()
    if bucket is not None:
        bucket.append({"type": kind, "value": val, "error": str(exc)})


def _safe_int(val: Any) -> int | None:
    """Coerce to int; unparseable values become NULL *and* are quarantined by the parser."""
    try:
        return to_int(val, nulls=NULL_TOKENS)
    except CoercionError as exc:
        _record_bad("int", val, exc)
        return None


def _safe_bool(val: Any) -> bool | None:
    """Coerce to bool; unparseable values become NULL *and* are quarantined by the parser."""
    try:
        return to_bool(val, nulls=NULL_TOKENS)
    except CoercionError as exc:
        _record_bad("bool", val, exc)
        return None


def quarantining(dataset: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator: collect uncoercible values during a parse call and quarantine them."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            bucket: list[dict[str, Any]] = []
            token = _BAD_VALUES.set(bucket)
            try:
                return func(*args, **kwargs)
            finally:
                _BAD_VALUES.reset(token)
                if bucket:
                    get_quarantine().write(
                        "retrosheet", dataset, bucket, f"{len(bucket)} uncoercible value(s)"
                    )

        return wrapper

    return decorator


def _load_league(paths: list[Path], year: int | None = None) -> League | None:
    """Load the season TEAM file for name resolution; failures are logged, not hidden."""
    if not paths:
        return None
    parent = paths[0].parent
    team_file = parent / f"TEAM{year}" if year else None
    if team_file and team_file.exists():
        try:
            league = League()
            league.read(team_file.read_bytes())
            return league
        except (ValueError, KeyError, IndexError, UnicodeDecodeError, OSError):
            logger.warning(
                "could not load Retrosheet team file %s; player/team names will be unresolved",
                team_file,
                exc_info=True,
            )
    return None


class RetrosheetEventParser:
    """Parses Retrosheet .EVA / .EVN / .EVE event files using pure-Python chadwickpy."""

    def __init__(self, league: League | None = None) -> None:
        self.league = league

    @quarantining("events")
    def parse_files(self, paths: list[Path], year: int | None = None) -> pa.Table:
        """Parse multiple event files into a consolidated typed PyArrow Table."""
        if not paths:
            return pa.Table.from_batches([], schema=RETROSHEET_EVENT_SCHEMA)

        league = self.league or _load_league(paths, year)

        records: list[dict[str, Any]] = []
        for path in paths:
            data = path.read_bytes()
            for raw_row in event_rows(data, league=league):
                casted_row: dict[str, Any] = {}
                for field in RETROSHEET_EVENT_SCHEMA:
                    col_name = field.name
                    target_type = field.type
                    val = raw_row.get(col_name)

                    if target_type == pa.bool_():
                        casted_row[col_name] = _safe_bool(val)
                    elif pa.types.is_integer(target_type):
                        casted_row[col_name] = _safe_int(val)
                    else:
                        casted_row[col_name] = str(val) if val is not None else None

                records.append(casted_row)

        if not records:
            return pa.Table.from_batches([], schema=RETROSHEET_EVENT_SCHEMA)

        arrays = []
        for field in RETROSHEET_EVENT_SCHEMA:
            col_name = field.name
            col_type = field.type
            col_vals = [r.get(col_name) for r in records]
            arrays.append(pa.array(col_vals, type=col_type))

        return pa.Table.from_arrays(arrays, schema=RETROSHEET_EVENT_SCHEMA)


class RetrosheetBoxScoreParser:
    """Parses game boxscores into Batting and Pitching PyArrow Tables via cwbox."""

    def __init__(self, league: League | None = None) -> None:
        self.league = league

    @quarantining("boxscores")
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
            for game, _, _ in iterate_games(data, league=league):
                game_id = game.game_id or ""
                vis_team = game.info_lookup("visteam") or ""
                home_team = game.info_lookup("hometeam") or ""
                box = box_create(game)

                # 1. Batting lines from slots
                for team_idx, team_code in enumerate((vis_team, home_team)):
                    for slot_idx in range(len(box.slots)):
                        player = box.slots[slot_idx][team_idx]
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
                    pitcher = box.pitchers[team_idx]
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
                col_type = field.type
                col_vals = [r.get(name) for r in records]
                arrays.append(pa.array(col_vals, type=col_type))
            return pa.Table.from_arrays(arrays, schema=schema)

        return (
            _build_table(batting_records, RETROSHEET_BOX_BATTING_SCHEMA),
            _build_table(pitching_records, RETROSHEET_BOX_PITCHING_SCHEMA),
        )


class RetrosheetDailySplitsParser:
    """Parses daily player appearance records via chadwickpy daily."""

    def __init__(self, league: League | None = None) -> None:
        self.league = league

    @quarantining("daily_splits")
    def parse_files(self, paths: list[Path], year: int | None = None) -> pa.Table:
        """Parse daily lines from event files."""
        if not paths:
            return pa.Table.from_batches([], schema=RETROSHEET_DAILY_SPLITS_SCHEMA)

        league = self.league or _load_league(paths, year)
        records: list[dict[str, Any]] = []

        for path in paths:
            data = path.read_bytes()
            for line in daily.daily_lines(data, league=league):
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
            arrays.append(pa.array(col_vals, type=target_type))

        return pa.Table.from_arrays(arrays, schema=RETROSHEET_DAILY_SPLITS_SCHEMA)


class RetrosheetSubstitutionsParser:
    """Parses in-game player substitutions via chadwickpy sub."""

    def __init__(self, league: League | None = None) -> None:
        self.league = league

    @quarantining("substitutions")
    def parse_files(self, paths: list[Path], year: int | None = None) -> pa.Table:
        """Parse substitutions from event files."""
        if not paths:
            return pa.Table.from_batches([], schema=RETROSHEET_SUBSTITUTIONS_SCHEMA)

        league = self.league or _load_league(paths, year)
        records: list[dict[str, Any]] = []

        for path in paths:
            data = path.read_bytes()
            for line in sub.sub_lines(data, league=league):
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
            arrays.append(pa.array(col_vals, type=target_type))

        return pa.Table.from_arrays(arrays, schema=RETROSHEET_SUBSTITUTIONS_SCHEMA)


class RetrosheetGameLogParser:
    """Parses 161-column Retrosheet Game Logs (glYYYY.txt) into strongly-typed PyArrow Tables."""

    @quarantining("gamelogs")
    def parse_file(self, path: Path) -> pa.Table:
        """Parse a game log file into PyArrow Table."""
        if not path.exists():
            return pa.Table.from_batches([], schema=RETROSHEET_GAMELOG_SCHEMA)

        text = path.read_text(encoding="utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        schema_fields = list(RETROSHEET_GAMELOG_SCHEMA)

        records: list[dict[str, Any]] = []
        for row in reader:
            if not row or len(row) < 10:
                continue
            rec: dict[str, Any] = {}
            for i, field in enumerate(schema_fields):
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

            records.append(rec)

        if not records:
            return pa.Table.from_batches([], schema=RETROSHEET_GAMELOG_SCHEMA)

        arrays = []
        for field in RETROSHEET_GAMELOG_SCHEMA:
            name = field.name
            target_type = field.type
            col_vals = [r.get(name) for r in records]
            arrays.append(pa.array(col_vals, type=target_type))

        return pa.Table.from_arrays(arrays, schema=RETROSHEET_GAMELOG_SCHEMA)


class RetrosheetRosterParser:
    """Parses Retrosheet roster files (.ROS) into PyArrow Tables."""

    @quarantining("rosters")
    def parse_files(self, paths: list[Path], year: int | None = None) -> pa.Table:
        """Parse one or more .ROS roster files."""
        records: list[dict[str, Any]] = []

        for path in paths:
            team_code = path.name[:3].upper() if len(path.name) >= 3 else ""
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 6:
                    records.append(
                        {
                            "player_id": parts[0],
                            "last_name": parts[1],
                            "first_name": parts[2],
                            "bats": parts[3],
                            "throws": parts[4],
                            "team": parts[5] if len(parts) > 5 else team_code,
                            "position": parts[6] if len(parts) > 6 else "",
                            "year": year,
                        }
                    )

        if not records:
            return pa.Table.from_batches([], schema=RETROSHEET_ROSTER_SCHEMA)

        arrays = []
        for field in RETROSHEET_ROSTER_SCHEMA:
            name = field.name
            target_type = field.type
            col_vals = [r.get(name) for r in records]
            arrays.append(pa.array(col_vals, type=target_type))

        return pa.Table.from_arrays(arrays, schema=RETROSHEET_ROSTER_SCHEMA)


class RetrosheetReferenceParser:
    """Parses reference CSV tables (ballparks, teams, ejections, coaches, relatives, biofile)."""

    SCHEMAS = {
        "ballparks": RETROSHEET_BALLPARKS_SCHEMA,
        "teams": RETROSHEET_TEAMS_SCHEMA,
        "ejections": RETROSHEET_EJECTIONS_SCHEMA,
        "coaches": RETROSHEET_COACHES_SCHEMA,
        "relatives": RETROSHEET_RELATIVES_SCHEMA,
        "biofile": RETROSHEET_BIOFILE_SCHEMA,
    }

    @quarantining("reference")
    def parse_file(self, table_name: str, path: Path) -> pa.Table:
        """Parse a reference CSV into PyArrow Table."""
        schema = self.SCHEMAS.get(table_name.lower())
        if not schema:
            raise ValueError(
                f"Unknown reference schema '{table_name}'. Valid schemas: {list(self.SCHEMAS.keys())}"
            )

        if not path.exists():
            return pa.Table.from_batches([], schema=schema)

        text = path.read_text(encoding="utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        header = next(reader, None)
        if not header:
            return pa.Table.from_batches([], schema=schema)

        # Schema-drift handling: the canonical schema is positional, so a header that is wider
        # than the schema must not lose data, and a narrower one must be reported.
        width = len(schema)
        if len(header) != width:
            logger.warning(
                "retrosheet reference %s: header has %d column(s) but schema expects %d; "
                "extra columns are preserved as strings, missing ones are NULL (header=%s)",
                table_name,
                len(header),
                width,
                header,
            )
        used = set(schema.names)
        extra_fields: list[pa.Field] = []
        for offset, raw_name in enumerate(header[width:]):
            clean = "_".join(raw_name.strip().lower().split()) or f"extra_{offset}"
            while clean in used:
                clean = f"{clean}_extra"
            used.add(clean)
            extra_fields.append(pa.field(clean, pa.string()))
        full_schema = pa.schema(list(schema) + extra_fields)

        records: list[dict[str, Any]] = []
        for row in reader:
            if not row:
                continue
            rec: dict[str, Any] = {}
            for i, field in enumerate(full_schema):
                val = row[i] if i < len(row) else None
                name = field.name

                if pa.types.is_integer(field.type):
                    rec[name] = _safe_int(val)
                else:
                    rec[name] = val if val else None
            records.append(rec)

        if not records:
            return pa.Table.from_batches([], schema=full_schema)

        arrays = [
            pa.array([r.get(field.name) for r in records], type=field.type) for field in full_schema
        ]
        return pa.Table.from_arrays(arrays, schema=full_schema)
