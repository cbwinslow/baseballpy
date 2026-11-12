"""Fetch Retrosheet's own bulk files politely, stage by stage (dev tool; change retrosheet-site-files).

    uv run python scripts/fetch_retrosheet_site.py --plan                  # list the files, request nothing
    uv run python scripts/fetch_retrosheet_site.py --group core            # fetch one group
    uv run python scripts/fetch_retrosheet_site.py --group bundles --max-gb 2

One request every four seconds, one connection, robots.txt obeyed, the first refusal stops the run. See
``baseballpy.sources.retrosheet.site`` for the rules and the reasons. Files land in
``$BASEBALLPY_HOME/raw/retrosheet/site_files/`` with their sha256 in the manifest. Retrosheet's notice asks for this credit
on anything built from its data: "The information used here was obtained free of charge from and is copyrighted by
Retrosheet."
"""

import argparse
import time

from baseballpy.core.config import LakeConfig
from baseballpy.sources.retrosheet.site import SITE_FILES, fetch_site_files, site_client


def main() -> int:
    """Run the fetcher for the chosen groups."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--group",
        action="append",
        default=[],
        help="core, bundles, discrepancies or officialtotals",
    )
    parser.add_argument("--plan", action="store_true", help="list the files and request nothing")
    parser.add_argument(
        "--max-gb", type=float, default=3.0, help="a file larger than this is skipped (default 3)"
    )
    parser.add_argument("--limit", type=int, default=None, help="fetch at most this many files")
    parser.add_argument(
        "--refresh", action="store_true", help="fetch files that are already stored again"
    )
    args = parser.parse_args()
    groups = args.group or ["core"]
    files = [f for f in SITE_FILES if f.group in groups]
    if args.limit is not None:
        files = files[: args.limit]
    print(f"{len(files)} file(s) in group(s) {', '.join(groups)}")
    if args.plan:
        for item in files:
            print(f"  {item.group:15} {item.url}  {item.note}")
        return 0
    client = site_client()
    started = time.perf_counter()
    try:
        report = fetch_site_files(
            client,
            LakeConfig(),
            files,
            refresh=args.refresh,
            max_bytes=int(args.max_gb * 1024**3),
        )
    finally:
        client.close()
    seconds = time.perf_counter() - started
    print(
        f"downloaded {len(report.downloaded)} file(s), {report.bytes / 1e6:,.1f} MB in {seconds:,.0f} s; "
        f"skipped {len(report.skipped)} (already stored); blocked by robots.txt {len(report.blocked)}; failed {len(report.failed)}"
    )
    for path in report.downloaded:
        print(f"  ok      {path}")
    for path, why in report.failed.items():
        print(f"  FAILED  {path}: {why}")
    for path in report.blocked:
        print(f"  BLOCKED {path}")
    if report.stopped:
        print(f"STOPPED: {report.stopped}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
