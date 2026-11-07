"""Copy the FanGraphs tables the owner already holds in the homelab database into the inbox.

Read only: one ``psql \\copy ... to stdout`` per table over ``ssh`` (key login, no password typed
here), gzipped on the homelab, written to ``<home>/inbox/fangraphs/<dataset>.csv.gz``. Nothing is
requested from FanGraphs. Rerun it to refresh the copy; then run ``baseballpy ingest fangraphs``.

    uv run python scripts/export_homelab_fangraphs.py [--host cbwdellr720] [--database mlb]
"""

import argparse
import re
import subprocess
import sys

from baseballpy.core.config import LakeConfig
from baseballpy.sources.fangraphs.files import BY_DATASET, FILES


def export(host: str, database: str, schema: str, table: str, target: str) -> int:
    """Stream one table as gzipped CSV to ``target``; returns the byte count."""
    for part in (database, schema, table):
        if not re.fullmatch(r"[A-Za-z0-9_]+", part):
            raise ValueError(f"not a plain database name: {part!r}")
    copy = f"\\copy (select * from {schema}.{table}) to stdout with csv header"  # noqa: S608 - names checked above
    remote = f'psql -d {database} -c "{copy}" | gzip -c'
    with open(target, "wb") as out:
        proc = subprocess.run(  # noqa: S603 - a fixed argument list
            ["ssh", "-o", "BatchMode=yes", host, remote],  # noqa: S607 - the user's own ssh client
            stdout=out,
            check=False,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"export of {schema}.{table} failed with exit code {proc.returncode}")
    with open(target, "rb") as handle:
        handle.seek(0, 2)
        return handle.tell()


def main() -> int:
    """Export the selected datasets (default: all)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="cbwdellr720")
    parser.add_argument("--database", default="mlb")
    parser.add_argument("--schema", default="raw")
    parser.add_argument("datasets", nargs="*", help="dataset names (default: all)")
    args = parser.parse_args()
    wanted = args.datasets or [f.dataset for f in FILES]
    unknown = [d for d in wanted if d not in BY_DATASET]
    if unknown:
        parser.error(f"unknown dataset(s) {unknown}; known: {sorted(BY_DATASET)}")
    inbox = LakeConfig().inbox_dir("fangraphs")
    inbox.mkdir(parents=True, exist_ok=True)
    for name in wanted:
        file = BY_DATASET[name]
        target = inbox / f"{name}.csv.gz"
        size = export(args.host, args.database, args.schema, file.homelab_table, str(target))
        print(f"{name}: {size / 1e6:,.1f} MB -> {target}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
