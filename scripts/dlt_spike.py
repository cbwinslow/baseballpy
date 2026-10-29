"""Compare loading MLB Stats API endpoints via dlt against the current flatten path.

Usage::

    uv run python scripts/dlt_spike.py [--workdir DIR] [--keep]

This is a standalone spike for OpenSpec change dlt-pipeline-core (task 1.1).
It loads three representative endpoints (teams_season, schedule_hydrated,
people_stats_season_hitting) through both dlt and iter_records, reporting
differences in rows, columns, child tables, types, and runtime.
"""

import argparse
import json
import shutil
import sys
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import dlt
import duckdb
import pyarrow.parquet as pq

from baseballpy.core.config import RateLimitConfig
from baseballpy.core.http import HttpClient, HttpStatusError
from baseballpy.sources.mlb_api.endpoints import (
    BY_NAME,
    MLB_BASE_URL,
    Context,
    MlbEndpoint,
    Request,
    requests_for,
)
from baseballpy.sources.mlb_api.flatten import iter_records

SCHEMA_CONTRACT: dict[str, str] = {
    "tables": "evolve",
    "columns": "evolve",
    "data_type": "evolve",
}


@dataclass(frozen=True)
class SpikeCase:
    """One test case comparing dlt with the current flatten path."""

    endpoint_name: str
    context: Context
    params_override: Mapping[str, str | int] = field(default_factory=dict)


CASES: tuple[SpikeCase, ...] = (
    SpikeCase(
        endpoint_name="teams_season",
        context=Context(season=2024, sport_ids=(1,)),
    ),
    SpikeCase(
        endpoint_name="schedule_hydrated",
        context=Context(season=2024, sport_ids=(1,)),
        params_override={"startDate": "2024-07-04", "endDate": "2024-07-04"},
    ),
    SpikeCase(
        endpoint_name="people_stats_season_hitting",
        context=Context(season=2024, person_ids=(592450, 543037, 660271)),
    ),
)


def select_records(node: Any, path: tuple[str, ...]) -> Iterator[dict[str, Any]]:
    """Yield raw record dicts found at ``path`` without flattening.

    Path semantics:
    - a string selects a dict key
    - "*" fans out over list elements
    - "@" fans out over dict values
    A missing key yields nothing.
    A shape that contradicts the path raises ValueError.
    """
    if not path:
        if isinstance(node, list):
            for item in node:
                if not isinstance(item, dict):
                    raise ValueError(f"expected dict record in list, got {type(item).__name__}")
                yield item
        elif isinstance(node, dict):
            yield node
        elif node is not None:
            raise ValueError(
                f"expected dict or list of dicts at record level, got {type(node).__name__}"
            )
        return

    head, rest = path[0], path[1:]

    if head == "*":
        if not isinstance(node, list):
            raise ValueError(f"expected list for '*' path segment, got {type(node).__name__}")
        for element in node:
            yield from select_records(element, rest)
        return

    if head == "@":
        if not isinstance(node, dict):
            raise ValueError(f"expected dict for '@' path segment, got {type(node).__name__}")
        for element in node.values():
            yield from select_records(element, rest)
        return

    if node is None:
        return

    if not isinstance(node, dict):
        raise ValueError(f"expected dict for key {head!r}, got {type(node).__name__}")

    if head not in node:
        return

    yield from select_records(node[head], rest)


def dlt_resource(
    endpoint: MlbEndpoint | Any,
    payloads: Sequence[tuple[Request | Any, Any]],
) -> Any:
    """Return a dlt.resource named endpoint.name yielding raw records with request extra merged.

    Write disposition is 'merge' with primary_key from endpoint.keys when every key
    is a top-level column present in the records; otherwise 'append'.
    """
    records: list[dict[str, Any]] = []
    for req, payload in payloads:
        extra = getattr(req, "extra", {}) or {}
        for rec in select_records(payload, endpoint.records):
            records.append({**rec, **extra})

    can_merge = bool(
        endpoint.keys and records and all(all(k in r for k in endpoint.keys) for r in records)
    )
    write_disposition = "merge" if can_merge else "append"
    primary_key = list(endpoint.keys) if can_merge else None

    return dlt.resource(
        records,
        name=endpoint.name,
        write_disposition=write_disposition,
        primary_key=primary_key,
    )


def _inspect_duckdb_tables(
    db_path: Path, dataset_name: str
) -> tuple[dict[str, dict[str, str]], dict[str, int]]:
    """Query table schemas and row counts from DuckDB information_schema."""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = ?
              AND table_name NOT LIKE '_dlt_%'
            ORDER BY table_name, ordinal_position
            """,
            [dataset_name],
        ).fetchall()

        tables_cols: dict[str, dict[str, str]] = {}
        for table_name, col_name, data_type in rows:
            if not col_name.startswith("_dlt_"):
                tables_cols.setdefault(table_name, {})[col_name] = data_type

        row_counts: dict[str, int] = {}
        for table_name in tables_cols:
            # identifiers come from information_schema of our own scratch database
            count = con.execute(
                f'SELECT COUNT(*) FROM "{dataset_name}"."{table_name}"'  # noqa: S608
            ).fetchone()
            row_counts[table_name] = count[0] if count else 0

        return tables_cols, row_counts
    finally:
        con.close()


def _inspect_parquet_types(parquet_dir: Path, table_name: str) -> dict[str, str]:
    """Read Parquet file schema for a table and return column -> Arrow type string."""
    files = sorted(parquet_dir.glob(f"**/{table_name}/*.parquet"))
    if not files:
        files = sorted(parquet_dir.glob(f"**/{table_name}*.parquet"))
    if not files:
        return {}
    schema = pq.read_table(files[0]).schema
    return {name: str(schema.field(name).type) for name in schema.names}


def _run_single_case(case: SpikeCase, http: HttpClient, workdir: Path) -> dict[str, Any]:
    """Execute both current and dlt paths for one case and return comparison metrics."""
    endpoint = BY_NAME[case.endpoint_name]

    # 1. Fetch payloads once
    requests: list[Request] = []
    for req in requests_for(endpoint, case.context):
        if case.params_override:
            merged_params = {**req.params, **case.params_override}
            req = replace(req, params=merged_params)
        requests.append(req)

    payloads: list[tuple[Request, Any]] = []
    for req in requests:
        url = f"{MLB_BASE_URL}/{req.path}"
        res = http.get_sync(url, params=req.params, allow=(200,))
        if res.status != 200:
            raise HttpStatusError(url, res.status)
        payload = json.loads(res.content)
        payloads.append((req, payload))

    # 2. Current-path side
    t0_current = time.perf_counter()
    current_rows = 0
    current_cols: set[str] = set()
    for req, payload in payloads:
        for rec in iter_records(payload, endpoint.records):
            current_rows += 1
            current_cols.update({**rec, **req.extra}.keys())
    t1_current = time.perf_counter()
    current_duration = t1_current - t0_current

    # 3. dlt side
    pipelines_dir = str(workdir / "pipelines")
    duckdb_path = workdir / "spike.duckdb"
    parquet_dir = workdir / "parquet"

    t0_dlt = time.perf_counter()
    pipe_duckdb = dlt.pipeline(
        pipeline_name=f"{case.endpoint_name}_duckdb",
        pipelines_dir=pipelines_dir,
        destination=dlt.destinations.duckdb(str(duckdb_path)),
        dataset_name=case.endpoint_name,
    )
    pipe_duckdb.run(
        dlt_resource(endpoint, payloads),
        schema_contract=SCHEMA_CONTRACT,
    )

    pipe_parquet = dlt.pipeline(
        pipeline_name=f"{case.endpoint_name}_parquet",
        pipelines_dir=pipelines_dir,
        destination=dlt.destinations.filesystem(str(parquet_dir)),
        dataset_name=case.endpoint_name,
    )
    pipe_parquet.run(
        dlt_resource(endpoint, payloads),
        loader_file_format="parquet",
        schema_contract=SCHEMA_CONTRACT,
    )
    t1_dlt = time.perf_counter()
    dlt_duration = t1_dlt - t0_dlt

    # 4. Inspect DuckDB results & Parquet types
    tables_cols, table_row_counts = _inspect_duckdb_tables(duckdb_path, case.endpoint_name)

    naming = pipe_duckdb.default_schema.naming
    main_table = case.endpoint_name
    child_tables = [t for t in tables_cols if t != main_table]

    mapped_current_cols = {naming.normalize_identifier(c.replace(".", "__")) for c in current_cols}
    dlt_main_cols = set(tables_cols.get(main_table, {}).keys())

    cols_current_has_dlt_lacks = sorted(mapped_current_cols - dlt_main_cols)
    cols_dlt_has_current_lacks = sorted(dlt_main_cols - mapped_current_cols)

    table_reports: dict[str, Any] = {}
    for table_name, cols_dict in tables_cols.items():
        arrow_types = _inspect_parquet_types(parquet_dir, table_name)
        col_type_pairs = {
            col: {
                "dlt_type": dlt_type,
                "arrow_type": arrow_types.get(col, "N/A"),
            }
            for col, dlt_type in cols_dict.items()
        }
        table_reports[table_name] = {
            "row_count": table_row_counts.get(table_name, 0),
            "column_count": len(cols_dict),
            "columns": col_type_pairs,
        }

    return {
        "endpoint": case.endpoint_name,
        "requests_count": len(requests),
        "current_path": {
            "rows": current_rows,
            "column_count": len(current_cols),
            "duration_seconds": round(current_duration, 4),
        },
        "dlt_path": {
            "duration_seconds": round(dlt_duration, 4),
            "main_table": main_table,
            "child_tables": child_tables,
            "tables": table_reports,
            "columns_current_has_dlt_lacks": cols_current_has_dlt_lacks,
            "columns_dlt_has_current_lacks": cols_dlt_has_current_lacks,
        },
    }


def _print_case_report(report: dict[str, Any]) -> None:
    """Print readable comparison report for one endpoint case."""
    name = report["endpoint"]
    cur = report["current_path"]
    dlt_res = report["dlt_path"]

    print(f"\n{'=' * 80}\nCASE: {name}\n{'=' * 80}")
    print(f"Requests made: {report['requests_count']}")
    print(f"\nCurrent Path:\n  Rows: {cur['rows']}\n  Columns: {cur['column_count']}")
    print(f"  Wall-clock time: {cur['duration_seconds']}s")

    print(f"\ndlt Path:\n  Wall-clock time: {dlt_res['duration_seconds']}s")
    print(f"  Child tables created: {', '.join(dlt_res['child_tables']) or '(none)'}")
    print("  Resulting tables:")
    for tbl_name, tbl_info in dlt_res["tables"].items():
        print(f"    * {tbl_name}: {tbl_info['row_count']} rows, {tbl_info['column_count']} cols")
        for col_name, type_info in tbl_info["columns"].items():
            print(f"        {col_name}: {type_info['dlt_type']} (Arrow: {type_info['arrow_type']})")

    cur_diff = dlt_res["columns_current_has_dlt_lacks"]
    dlt_diff = dlt_res["columns_dlt_has_current_lacks"]
    print(f"\nColumn differences for main table ({dlt_res['main_table']}):")
    print(f"  Current path has that dlt lacks ({len(cur_diff)}): {', '.join(cur_diff) or '(none)'}")
    print(f"  dlt has that current path lacks ({len(dlt_diff)}): {', '.join(dlt_diff) or '(none)'}")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the dlt spike runner."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workdir",
        type=str,
        default=None,
        help="Custom work directory (must be outside repo)",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep temporary workdir upon completion",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent

    if args.workdir:
        workdir = Path(args.workdir).resolve()
        workdir.mkdir(parents=True, exist_ok=True)
        cleanup = False
    else:
        workdir = Path(tempfile.mkdtemp(prefix="baseballpy_dlt_spike_")).resolve()
        cleanup = not args.keep

    if workdir == repo_root or repo_root in workdir.parents:
        print(f"Error: workdir cannot be inside the repository: {workdir}", file=sys.stderr)
        return 1

    http = HttpClient(RateLimitConfig())
    all_reports: list[dict[str, Any]] = []

    try:
        for case in CASES:
            report = _run_single_case(case, http, workdir)
            all_reports.append(report)
            _print_case_report(report)

        report_file = workdir / "report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(all_reports, f, indent=2)
        print(f"\nSummary report written to {report_file}")
        return 0
    finally:
        http.close()
        if cleanup and workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
