"""Retrosheet parsers bridging chadwickpy into strongly-typed PyArrow Tables."""

import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
from chadwickpy.roster import League
from chadwickpy.tools.events import event_rows

from baseballpy.sources.retrosheet.schema import (
    RETROSHEET_EVENT_SCHEMA,
    RETROSHEET_GAMELOG_SCHEMA,
    RETROSHEET_ROSTER_SCHEMA,
)


def _safe_int(val: Any) -> int | None:
    if val is None or val == "" or val == "null":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_bool(val: Any) -> bool | None:
    if val is None or val == "" or val == "null":
        return None
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("1", "t", "true", "y"):
        return True
    if s in ("0", "f", "false", "n"):
        return False
    return None


class RetrosheetEventParser:
    """Parses Retrosheet .EVA / .EVN event files using pure-Python chadwickpy."""

    def __init__(self, league: League | None = None) -> None:
        self.league = league

    def parse_files(self, paths: list[Path], year: int | None = None) -> pa.Table:
        """Parse multiple event files into a consolidated typed PyArrow Table."""
        if not paths:
            return pa.Table.from_batches([], schema=RETROSHEET_EVENT_SCHEMA)

        # Initialize League from TEAM manifest if present
        league = self.league
        if league is None and paths:
            parent = paths[0].parent
            team_file = parent / f"TEAM{year}" if year else None
            if team_file and team_file.exists():
                try:
                    league = League()
                    league.read(team_file.read_bytes())
                except Exception:
                    league = None

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


class RetrosheetGameLogParser:
    """Parses 161-column Retrosheet Game Logs (glYYYY.txt) into strongly-typed PyArrow Tables."""

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
