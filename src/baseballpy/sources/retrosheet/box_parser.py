"""Parse Retrosheet box-score game accounts (``seasons/<Y>/<Y>.EBA|EBN|EBE|EBR|EBF``).

Layouts verified against the real files (6,194 games in the 1950 and 2023 files); the official
description is ``https://www.retrosheet.org/boxfile.txt`` (not reachable from the build
environment, see OpenSpec change ``retrosheet-box-accounts``). Verified kinds are typed:

* ``id`` / ``version`` / ``info,<key>,<value>`` -> ``box_games`` (one row per game)
* ``start,<id>,"<name>",<side>,<order>,<pos>`` -> ``box_starters``
* ``stat,bline,<id>,<side>,<pos>,<seq>,<17 counting stats>`` -> ``box_batting_lines``

Every other record (``stat,phline|prline|dline|pline|tline``, ``line``, ``event,*``, ``com``, and
any unknown kind) is kept losslessly in ``box_records`` (kind, parsed fields, raw line) until its
column names are confirmed against the official document.
"""

import csv
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pyarrow as pa

from baseballpy.core.quarantine import (
    collect_bad_values,
    record_bad_value,
    safe_array,
)
from baseballpy.core.schema_tools import schema_from_columns

BLINE_STATS = (
    "ab", "r", "h", "double", "triple", "hr", "rbi", "sh", "sf", "hbp", "bb", "ibb", "k",
    "sb", "cs", "gidp", "interference",
)  # fmt: skip
#: ``info`` keys with their own column; anything else lands in ``_extras``
INFO_COLUMNS: tuple[tuple[str, str], ...] = (
    ("visteam", "string"),
    ("hometeam", "string"),
    ("date", "date32:%Y/%m/%d"),
    ("number", "int16"),
    ("starttime", "string"),
    ("daynight", "string"),
    ("usedh", "bool"),
    ("umphome", "string"),
    ("ump1b", "string"),
    ("ump2b", "string"),
    ("ump3b", "string"),
    ("umplf", "string"),
    ("umprf", "string"),
    ("site", "string"),
    ("attendance", "int32"),
    ("temp", "int16"),
    ("winddir", "string"),
    ("windspeed", "int16"),
    ("fieldcond", "string"),
    ("precip", "string"),
    ("sky", "string"),
    ("timeofgame", "int16"),
    ("innings", "int16"),
    ("tiebreaker", "string"),
    ("gametype", "string"),
    ("wp", "string"),
    ("lp", "string"),
    ("save", "string"),
    ("gwrbi", "string"),
    ("oscorer", "string"),
)
_SENTINELS = frozenset({"", "unknown"})

BOX_GAMES_SCHEMA = schema_from_columns(
    [("game_id", "string"), ("version", "int16"), *INFO_COLUMNS, ("source_file", "string")]
)
BOX_STARTERS_SCHEMA = schema_from_columns(
    [
        ("game_id", "string"),
        ("player_id", "string"),
        ("player_name", "string"),
        ("side", "int8"),
        ("batting_order", "int8"),
        ("position", "int8"),
    ],
    extras=False,
)
_BLINE_TYPES = [("ab", "int16")] + [(c, "int16") for c in BLINE_STATS[1:]]
BOX_BATTING_SCHEMA = schema_from_columns(
    [
        ("game_id", "string"),
        ("player_id", "string"),
        ("side", "int8"),
        ("position", "int8"),
        ("seq", "int8"),
        *_BLINE_TYPES,
    ],
    extras=False,
)
BOX_RECORDS_SCHEMA = pa.schema(
    [
        ("game_id", pa.string()),
        ("line_no", pa.int32()),
        ("kind", pa.string()),
        ("fields", pa.list_(pa.string())),
        ("raw", pa.string()),
    ]
)
SCHEMAS = {
    "box_games": BOX_GAMES_SCHEMA,
    "box_starters": BOX_STARTERS_SCHEMA,
    "box_batting_lines": BOX_BATTING_SCHEMA,
    "box_records": BOX_RECORDS_SCHEMA,
}


class BoxParseError(ValueError):
    """A box-score record does not have the layout verified for its kind."""


@dataclass
class _Game:
    game_id: str
    version: int | None = None
    info: dict[str, str] = field(default_factory=dict)


@dataclass
class BoxTables:
    """The four tables parsed from one box-account file."""

    games: pa.Table
    starters: pa.Table
    batting: pa.Table
    records: pa.Table

    def by_name(self) -> dict[str, pa.Table]:
        """Tables keyed by dataset name."""
        return {
            "box_games": self.games,
            "box_starters": self.starters,
            "box_batting_lines": self.batting,
            "box_records": self.records,
        }


def _fields(line: str) -> list[str]:
    try:
        return next(csv.reader([line]))
    except (csv.Error, StopIteration) as exc:  # pragma: no cover - csv accepts any text line
        raise BoxParseError(f"unreadable line {line!r}: {exc}") from exc


def _info_value(kind: str, value: str) -> Any:
    if value in _SENTINELS:
        return None
    if kind == "bool":
        if value not in ("true", "false"):
            raise BoxParseError(f"boolean info value {value!r}")
        return value == "true"
    if kind.startswith("int"):
        try:
            return int(value)
        except ValueError as exc:
            raise BoxParseError(f"integer info value {value!r} for kind {kind!r}") from exc
    return value


def _ints(values: list[str], number: int, what: str) -> list[int]:
    """The integers in ``values``; a non-integer raises :class:`BoxParseError` naming the line."""
    try:
        return [int(v) for v in values]
    except ValueError as exc:
        raise BoxParseError(f"line {number}: {what} record has an invalid integer: {exc}") from exc


def _as_date(value: Any) -> date | None:
    """A box-account date (``YYYY/M/D`` with or without zero padding); a bad one is quarantined."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y/%m/%d").date()
    except ValueError as exc:
        record_bad_value("date", value, exc)
        return None


def decode_box(data: bytes) -> str:
    """Decode a box-account file: UTF-8 (all files seen so far), Latin-1 as the documented fallback."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


@collect_bad_values("retrosheet", "box_games")
def parse_box_text(text: str, source_file: str = "") -> BoxTables:
    """Parse one box-account file's text into the four tables (strict field counts)."""
    games: list[_Game] = []
    starters: list[list[Any]] = []
    batting: list[list[Any]] = []
    records: list[list[Any]] = []
    current: _Game | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        parts = _fields(line)
        kind = parts[0]
        if kind == "id":
            if len(parts) != 2:
                raise BoxParseError(f"line {number}: id record has {len(parts)} fields")
            current = _Game(parts[1])
            games.append(current)
            continue
        if current is None:
            raise BoxParseError(f"line {number}: {kind!r} record before any id record")
        if kind == "version":
            current.version = _ints([parts[1]], number, "version")[0]
        elif kind == "info":
            if len(parts) != 3:
                raise BoxParseError(f"line {number}: info record has {len(parts)} fields")
            if parts[1] not in current.info:
                current.info[parts[1]] = parts[2]
            else:
                records.append([current.game_id, number, "info", parts[1:], line])
        elif kind == "start":
            if len(parts) != 6:
                raise BoxParseError(f"line {number}: start record has {len(parts)} fields")
            starters.append(
                [current.game_id, parts[1], parts[2], *_ints(parts[3:], number, "start")]
            )
        elif kind == "stat" and len(parts) > 1 and parts[1] == "bline":
            if len(parts) != 23:
                raise BoxParseError(f"line {number}: bline record has {len(parts)} fields")
            batting.append([current.game_id, parts[2], *_ints(parts[3:], number, "bline")])
        else:
            typed = kind in ("stat", "event") and len(parts) > 1
            label = f"{kind},{parts[1]}" if typed else kind
            records.append(
                [current.game_id, number, label, parts[2:] if typed else parts[1:], line]
            )

    def column(rows: list[list[Any]], index: int, schema: pa.Schema, dataset: str) -> pa.Array:
        field_ = schema.field(index)
        return safe_array(
            [r[index] for r in rows],
            field_.type,
            source="retrosheet",
            dataset=dataset,
            column=field_.name,
        )

    known = {k for k, _ in INFO_COLUMNS}
    game_rows: list[dict[str, Any]] = []
    for g in games:
        row: dict[str, Any] = {
            "game_id": g.game_id,
            "version": g.version,
            "source_file": source_file,
        }
        for key, kind in INFO_COLUMNS:
            row[key] = _info_value(kind, g.info[key]) if key in g.info else None
        extra = {k: v for k, v in g.info.items() if k not in known}
        row["_extras"] = json.dumps(extra) if extra else None
        game_rows.append(row)
    game_arrays = []
    for f in BOX_GAMES_SCHEMA:
        values = [r[f.name] for r in game_rows]
        if pa.types.is_date32(f.type):
            dates = [_as_date(v) for v in values]
            game_arrays.append(pa.array(dates, pa.date32()))
        else:
            game_arrays.append(
                safe_array(values, f.type, source="retrosheet", dataset="box_games", column=f.name)
            )
    return BoxTables(
        games=pa.Table.from_arrays(game_arrays, schema=BOX_GAMES_SCHEMA),
        starters=pa.Table.from_arrays(
            [column(starters, i, BOX_STARTERS_SCHEMA, "box_starters") for i in range(6)],
            schema=BOX_STARTERS_SCHEMA,
        ),
        batting=pa.Table.from_arrays(
            [
                column(batting, i, BOX_BATTING_SCHEMA, "box_batting_lines")
                for i in range(len(BOX_BATTING_SCHEMA))
            ],
            schema=BOX_BATTING_SCHEMA,
        ),
        records=pa.Table.from_arrays(
            [column(records, i, BOX_RECORDS_SCHEMA, "box_records") for i in range(5)],
            schema=BOX_RECORDS_SCHEMA,
        ),
    )
