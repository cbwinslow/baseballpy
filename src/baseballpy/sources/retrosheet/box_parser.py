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
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pyarrow as pa

from baseballpy.core.coerce import NULL_TOKENS
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
    ("attendance_qualifier", "string"),
    ("temp", "int16"),
    ("winddir", "string"),
    ("windspeed", "int16"),
    ("fieldcond", "string"),
    ("precip", "string"),
    ("sky", "string"),
    ("timeofgame", "int16"),
    ("innings", "int16"),
    ("tiebreaker", "int16"),
    ("gametype", "string"),
    ("wp", "string"),
    ("lp", "string"),
    ("save", "string"),
    ("gwrbi", "string"),
    ("oscorer", "string"),
)
_SENTINELS = frozenset({"", "unknown"}) | NULL_TOKENS

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
_BLINE_COLUMNS: list[tuple[str, str]] = [
    ("ab", "int16"),
    ("r", "int16"),
    ("h", "int16"),
    ("double", "int16"),
    ("triple", "int16"),
    ("hr", "int16"),
    ("rbi", "int16"),
    ("rbi_qualifier", "string"),
    ("sh", "int16"),
    ("sf", "int16"),
    ("hbp", "int16"),
    ("bb", "int16"),
    ("ibb", "int16"),
    ("k", "int16"),
    ("sb", "int16"),
    ("cs", "int16"),
    ("gidp", "int16"),
    ("interference", "int16"),
]
BOX_BATTING_SCHEMA = schema_from_columns(
    [
        ("game_id", "string"),
        ("player_id", "string"),
        ("side", "int8"),
        ("position", "int8"),
        ("seq", "int8"),
        *_BLINE_COLUMNS,
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
    """A typed ``info`` value; one that does not fit its kind is quarantined and stored as NULL."""
    if value.strip() in _SENTINELS:
        return None
    if kind == "bool":
        lowered = value.strip().lower()
        if lowered not in ("true", "false"):
            record_bad_value("bool", value, f"boolean info value {value!r}")
            return None
        return lowered == "true"
    if kind.startswith("int"):
        try:
            return int(value)
        except ValueError as exc:
            record_bad_value(kind, value, exc)
            return None
    return value


def _parse_qualifier(val: Any) -> tuple[Any, str | None]:
    """Parse an integer value with optional historical qualifier (e.g. '2i' -> (2, 'inferred'))."""
    if val is None:
        return None, None
    if isinstance(val, int):
        return val, None
    text = str(val).strip()
    if not text or text in _SENTINELS:
        return None, None
    m = re.match(r"^(-?\d+)(.*)$", text)
    if m:
        num = int(m.group(1))
        suffix = m.group(2).strip()
        if suffix == "i":
            qualifier = "inferred"
        elif suffix in ("c.", "c", "circa"):
            qualifier = "circa"
        elif suffix in ("?", "uncertain"):
            qualifier = "uncertain"
        elif suffix in ("est", "est."):
            qualifier = "estimated"
        elif suffix:
            qualifier = suffix
        else:
            qualifier = None
        return num, qualifier
    return val, None


def _ints(values: list[str], number: int, what: str) -> list[Any]:
    """The integers in ``values``; sentinels/null tokens become None, unparseable text is kept for safe_array.

    Old box accounts hold stray cells such as ``2i``, ``NA`` or an empty field in numeric
    positions; null tokens become NULL in the table without failing the season.
    """
    out: list[Any] = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        text = str(v).strip()
        if not text or text in _SENTINELS:
            out.append(None)
            continue
        try:
            out.append(int(text))
        except ValueError:
            out.append(text)
    return out


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
    games, starters, batting, records = _scan(text)
    return BoxTables(
        games=_games_table(games, source_file),
        starters=_table(starters, BOX_STARTERS_SCHEMA, "box_starters"),
        batting=_table(batting, BOX_BATTING_SCHEMA, "box_batting_lines"),
        records=_table(records, BOX_RECORDS_SCHEMA, "box_records"),
    )


_Rows = list[list[Any]]


def _scan(text: str) -> tuple[list[_Game], _Rows, _Rows, _Rows]:
    """Read every line into games, starters, batting lines and generic records."""
    games: list[_Game] = []
    starters: _Rows = []
    batting: _Rows = []
    records: _Rows = []
    current: _Game | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        parts = _fields(line)
        if parts[0] == "id":
            if len(parts) != 2:
                raise BoxParseError(f"line {number}: id record has {len(parts)} fields")
            current = _Game(parts[1])
            games.append(current)
            continue
        if current is None:
            raise BoxParseError(f"line {number}: {parts[0]!r} record before any id record")
        _read_record(current, parts, number, line, starters, batting, records)
    return games, starters, batting, records


def _read_record(
    current: _Game,
    parts: list[str],
    number: int,
    line: str,
    starters: _Rows,
    batting: _Rows,
    records: _Rows,
) -> None:
    """Route one non-``id`` line of the game ``current`` to its table."""
    kind = parts[0]
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
        starters.append([current.game_id, parts[1], parts[2], *_ints(parts[3:], number, "start")])
    elif kind == "stat" and len(parts) > 1 and parts[1] == "bline":
        if len(parts) != 23:
            raise BoxParseError(f"line {number}: bline record has {len(parts)} fields")
        rbi_num, rbi_qual = _parse_qualifier(parts[12])
        batting_row = (
            [current.game_id, parts[2]]
            + _ints(parts[3:6], number, "bline")
            + _ints(parts[6:12], number, "bline")
            + [rbi_num, rbi_qual]
            + _ints(parts[13:], number, "bline")
        )
        batting.append(batting_row)
    else:
        typed = kind in ("stat", "event") and len(parts) > 1
        label = f"{kind},{parts[1]}" if typed else kind
        records.append([current.game_id, number, label, parts[2:] if typed else parts[1:], line])


def _column(rows: _Rows, index: int, schema: pa.Schema, dataset: str) -> pa.Array:
    """Column ``index`` of ``rows`` cast to the schema's type (bad cells are quarantined)."""
    field_ = schema.field(index)
    return safe_array(
        [r[index] for r in rows],
        field_.type,
        source="retrosheet",
        dataset=dataset,
        column=field_.name,
    )


def _table(rows: _Rows, schema: pa.Schema, dataset: str) -> pa.Table:
    return pa.Table.from_arrays(
        [_column(rows, i, schema, dataset) for i in range(len(schema))], schema=schema
    )


def _games_table(games: list[_Game], source_file: str) -> pa.Table:
    """One row per game: the typed ``info`` columns, the rest of the info as ``_extras``."""
    known = {k for k, _ in INFO_COLUMNS}
    game_rows: list[dict[str, Any]] = []
    for g in games:
        row: dict[str, Any] = {
            "game_id": g.game_id,
            "version": g.version,
            "source_file": source_file,
        }
        att_num: Any = None
        att_qual: str | None = None
        if "attendance" in g.info:
            att_num, att_qual = _parse_qualifier(g.info["attendance"])

        for key, kind in INFO_COLUMNS:
            if key == "attendance":
                row["attendance"] = att_num
            elif key == "attendance_qualifier":
                row["attendance_qualifier"] = att_qual
            else:
                row[key] = _info_value(kind, g.info[key]) if key in g.info else None
        extra = {k: v for k, v in g.info.items() if k not in known}
        row["_extras"] = json.dumps(extra) if extra else None
        game_rows.append(row)
    game_arrays = []
    for f in BOX_GAMES_SCHEMA:
        values = [r[f.name] for r in game_rows]
        if pa.types.is_date32(f.type):
            game_arrays.append(pa.array([_as_date(v) for v in values], pa.date32()))
        else:
            game_arrays.append(
                safe_array(values, f.type, source="retrosheet", dataset="box_games", column=f.name)
            )
    return pa.Table.from_arrays(game_arrays, schema=BOX_GAMES_SCHEMA)
