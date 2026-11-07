"""Plain-dict helpers that shape FanGraphs JSON into the columns the typed tables use.

The tables keep the names the existing files use: a key is lowercased, anything that is not a
letter, digit or underscore becomes ``_``, and a name that would start with a digit gets an ``n``
(``1B`` is ``n1b``, ``BB%`` is ``bb_``, ``xMLBAMID`` is ``xmlbamid``). Four key pairs that would
collide are renamed first. Because the same rule is applied to the website's JSON, a downloaded
season lands in the same typed columns as a file you supplied.
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from baseballpy.sources.fangraphs.web import COLUMN_RENAMES

_NOT_IDENTIFIER = re.compile(r"[^a-z0-9_]")


def column_name(name: str) -> str:
    """The table column for a FanGraphs key (see the module text)."""
    cleaned = _NOT_IDENTIFIER.sub("_", COLUMN_RENAMES.get(name, name).lower())
    if not cleaned.strip("_"):
        raise ValueError(f"FanGraphs key {name!r} has no letters or digits")
    return f"n{cleaned}" if cleaned[0].isdigit() else cleaned


def shape_row(row: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """One record with table column names, plus the bookkeeping columns in ``extra``.

    Two keys that end up with the same column name are an error: merging them would lose data.
    """
    out = {column_name(k): v for k, v in row.items()}
    if len(out) != len(row):
        raise ValueError(f"FanGraphs keys collide after renaming: {sorted(row)[:5]}...")
    return {**out, **extra}


def now_stamp() -> str:
    """UTC time as text, the form the ``_loaded_at`` column holds (``2026-11-06 12:00:00.123+00``)."""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "+00"


def projection_hash(row: dict[str, Any]) -> str:
    """md5 of a projection row's values (the keys FanGraphs sent, bookkeeping left out).

    A new snapshot row is stored only when this differs from the player's last stored hash. It is
    not a security hash, only a change marker; it matches the hash the existing files carry.
    """
    payload = {k: v for k, v in row.items() if not str(k).startswith("_")}
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.md5(blob.encode(), usedforsecurity=False).hexdigest()


__all__ = ["column_name", "now_stamp", "projection_hash", "shape_row"]
