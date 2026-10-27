"""Probe every Savant leaderboard variant live and generate strict schemas (dev tool).

Usage::

    uv run python scripts/gen_savant_schemas.py [--out src/baseballpy/sources/statcast/lb_tables.py]
                                               [--probe-out docs/savant_probe.json]

For each supported variant in :mod:`baseballpy.sources.statcast.lb_catalog` the script requests a
set of seasons through the shared ``HttpClient``, finds the first season with data (``min_year``),
widens column types across every non-empty season (int < float < string; never ``int8``), verifies
the documented key is unique within each season, and chooses the widest ``min`` qualifier.
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow as pa

from baseballpy.core.config import RateLimitConfig
from baseballpy.core.http import HttpClient, HttpStatusError, TransportError
from baseballpy.core.schema_tools import infer_type_name, read_csv_strings, snake
from baseballpy.sources.statcast.lb_catalog import (
    SAVANT_BASE,
    SUPPORTED,
    LeaderboardDef,
    request_params,
)
from baseballpy.sources.statcast.lb_parse import html_json_to_csv

SAMPLE_YEARS = (2008, 2012, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025)
MIN_CANDIDATES = ("0", "1", "q")
_RANK = {"int16": 0, "int32": 1, "int64": 2, "float64": 3, "string": 4}


def fetch(http: HttpClient, defn: LeaderboardDef, year: int, min_value: str | None) -> bytes | None:
    """CSV bytes for one season, or ``None`` when the route answers non-200/non-data."""
    url = f"{SAVANT_BASE}/{defn.route}"
    try:
        res = http.get_sync(
            url, params=request_params(defn, year, min_value), allow=(200, 400, 404)
        )
    except (HttpStatusError, TransportError):
        return None
    if res.status != 200:
        return None
    if defn.fmt == "html_json":
        try:
            return html_json_to_csv(res.content)
        except ValueError:
            return None
    head = res.content[:200].lstrip()
    if head.startswith(b"<") or b"," not in res.content.split(b"\n", 1)[0]:
        return None
    return res.content


def row_count(csv_bytes: bytes) -> int:
    """Data rows in a CSV payload."""
    return read_csv_strings(csv_bytes).num_rows


def widen(a: str, b: str) -> str:
    """The wider of two inferred type names."""
    return a if _RANK[a] >= _RANK[b] else b


def is_unique(table: pa.Table, keys: tuple[str, ...], names: dict[str, str]) -> bool:
    """True when ``keys`` identify every row exactly once."""
    cols = [table.column(names[k]).to_pylist() for k in keys]
    return len(set(zip(*cols, strict=True))) == table.num_rows


def profile(http: HttpClient, defn: LeaderboardDef, years: tuple[int, ...]) -> dict[str, Any]:
    """Probe one variant over ``years``: min qualifier, per-season rows, widened column types."""
    out: dict[str, Any] = {"slug": defn.slug, "route": defn.route}
    min_value: str | None = None
    if defn.min_param is not None:
        best = -1
        for cand in MIN_CANDIDATES:
            data = fetch(http, defn, 2024, cand)
            n = row_count(data) if data else -1
            if n > best:
                best, min_value = n, cand
    out["min"] = min_value
    columns: dict[str, str | None] = {}
    order: list[str] = []
    upstream: dict[str, str] = {}
    per_year: dict[int, int] = {}
    key_ok: dict[int, bool] = {}
    digests: dict[str, list[int]] = {}
    for year in years:
        data = fetch(http, defn, year, min_value)
        if data is None:
            per_year[year] = -1
            continue
        digests.setdefault(hashlib.md5(data).hexdigest(), []).append(year)
        table = read_csv_strings(data)
        per_year[year] = table.num_rows
        snaked = [snake(h) for h in table.column_names]
        for raw, name in zip(table.column_names, snaked, strict=True):
            col_type = infer_type_name(table.column(raw).to_pylist()) if table.num_rows else None
            if name not in columns:
                order.append(name)
                upstream[name] = raw
                columns[name] = col_type
            elif col_type is not None:
                current = columns[name]
                columns[name] = col_type if current is None else widen(current, col_type)
        if table.num_rows:
            by_name = dict(zip(snaked, table.column_names, strict=True))
            try:
                key_ok[year] = is_unique(table, defn.keys, {k: by_name[k] for k in defn.keys})
            except KeyError:
                key_ok[year] = False
    nonempty = [y for y, n in per_year.items() if n > 0]
    out["per_year_rows"] = per_year
    out["identical_years"] = [ys for ys in digests.values() if len(ys) > 1]
    out["min_year"] = min(nonempty) if nonempty else None
    out["max_year"] = max(nonempty) if nonempty else None
    out["key_unique"] = key_ok
    out["columns"] = [(n, columns[n] or "string", upstream[n]) for n in order]
    return out


def render(results: list[dict[str, Any]]) -> str:
    """Render the generated ``lb_tables.py`` module text."""
    lines = [
        '"""GENERATED by scripts/gen_savant_schemas.py from live Savant CSVs. Do not edit.',
        "",
        "``LEADERBOARD_COLUMNS`` maps slug -> ((column, type_name, upstream_header), ...);",
        "``LEADERBOARD_META`` records the first season with data and the widest ``min`` qualifier.",
        '"""',
        "",
        "LEADERBOARD_COLUMNS: dict[str, tuple[tuple[str, str, str], ...]] = {",
    ]
    for r in results:
        lines.append(f'    "{r["slug"]}": (')
        for name, typ, up in r["columns"]:
            lines.append(f'        ("{name}", "{typ}", {json.dumps(up)}),')
        lines.append("    ),")
    lines += ["}", "", "LEADERBOARD_META: dict[str, dict[str, int | str | None]] = {"]
    for r in results:
        lines.append(
            f'    "{r["slug"]}": {{"min_year": {r["min_year"]!r}, '
            f'"max_year_probed": {r["max_year"]!r}, "min": {r["min"]!r}}},'
        )
    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="src/baseballpy/sources/statcast/lb_tables.py")
    parser.add_argument("--probe-out", default="docs/savant_probe.json")
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--check", action="store_true", help="probe only, write nothing")
    args = parser.parse_args()
    http = HttpClient(RateLimitConfig())
    years = tuple(y for y in SAMPLE_YEARS if y <= date.today().year)
    results = []
    for defn in SUPPORTED:
        if args.only and defn.slug not in args.only:
            continue
        started = time.perf_counter()
        result = profile(http, defn, years)
        bad = [y for y, ok in result["key_unique"].items() if not ok]
        if result["identical_years"]:
            print(f"   !! year ignored? identical payloads for {result['identical_years']}")
        print(
            f"{defn.slug:34s} min_year={result['min_year']} cols={len(result['columns']):3d} "
            f"min={result['min']} key_not_unique={bad} ({time.perf_counter() - started:.0f}s)",
            flush=True,
        )
        results.append(result)
    if not args.only and not args.check:
        Path(args.out).write_text(render(results), encoding="utf-8")
        probe = {
            "probed_on": date.today().isoformat(),
            "leaderboards": {
                r["slug"]: {
                    k: r[k]
                    for k in ("route", "min", "min_year", "max_year", "per_year_rows", "key_unique")
                }
                for r in results
            },
        }
        Path(args.probe_out).write_text(json.dumps(probe, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
