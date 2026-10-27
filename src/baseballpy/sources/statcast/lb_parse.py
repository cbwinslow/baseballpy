"""Parse Savant leaderboard payloads that are not plain ``csv=true`` downloads."""

import csv
import io
import json
import re
from typing import Any


def _rows(value: Any, name: str) -> list[dict[str, Any]]:
    """The flat row objects of an embedded value: a list of objects, or a dict of such lists."""
    if isinstance(value, dict):
        merged: list[dict[str, Any]] = []
        for part in value.values():
            if not isinstance(part, list) or not all(isinstance(r, dict) for r in part):
                raise ValueError(
                    f"embedded `{name}` is a dict whose values are not lists of objects"
                )
            merged.extend(part)
        return merged
    if isinstance(value, list) and all(isinstance(r, dict) for r in value):
        return value
    raise ValueError(f"embedded `{name}` is not a list of objects")


def embedded_value(content: bytes, name: str = "data") -> Any:
    """The JSON value assigned to ``var/const/let <name>`` in a page (``ValueError`` if absent)."""
    text = content.decode("utf-8", errors="replace")
    pattern = r"\b(?:var|const|let)\s+" + re.escape(name) + r"\s*=\s*([\[{])"
    match = re.search(pattern, text)
    if match is None:
        raise ValueError(f"no `{name} = [...]` value found in the page")
    try:
        value, _ = json.JSONDecoder().raw_decode(text, match.start(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"embedded `{name}` is not valid JSON: {exc}") from exc
    return value


def html_json_to_csv(content: bytes, name: str = "data") -> bytes:
    """Turn the ``var/const/let <name> = [...]`` (or ``{...}`` of lists) embedded in a page into CSV.

    Raises ``ValueError`` when the page has no such value or it is not rows of flat objects (a
    changed page must fail loudly, never produce an empty table).
    """
    rows = _rows(embedded_value(content, name), name)
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(["" if row.get(c) is None else row.get(c) for c in columns])
    return buf.getvalue().encode("utf-8")
