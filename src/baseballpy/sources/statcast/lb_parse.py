"""Parse Savant leaderboard payloads that are not plain ``csv=true`` downloads."""

import csv
import io
import json
import re

_DATA_VAR = re.compile(r"\bvar\s+data\s*=\s*(\[)")


def html_json_to_csv(content: bytes) -> bytes:
    """Turn the ``var data = [{...}, ...];`` array embedded in a Savant page into CSV bytes.

    Raises ``ValueError`` when the page has no such array or it is not a list of flat objects
    (a changed page must fail loudly, never produce an empty table).
    """
    text = content.decode("utf-8", errors="replace")
    match = _DATA_VAR.search(text)
    if match is None:
        raise ValueError("no `var data = [...]` array found in the page")
    try:
        rows, _ = json.JSONDecoder().raw_decode(text, match.start(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"embedded data array is not valid JSON: {exc}") from exc
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("embedded data is not a list of objects")
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
