"""Read-only: which hydrate pool chunks the offline re-parse (ADR 130) would rebuild, and how many rows.

Usage: ``BASEBALLPY_HOME=<lake> uv run python scripts/hydrate_reparse_dry_run.py [--verify]``.
Writes nothing. A chunk counts when it is a league-wide ``v1/stats`` pool chunk the hydrate route
filled (``via`` or its raw file names) and its parser version or schema digest is not today's.
``--verify`` also checks the sha256 of every raw page (slow on a big lake).
"""

from __future__ import annotations

import argparse

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.stores import RawStore, schema_matches
from baseballpy.sources import catalog
from baseballpy.sources.mlb_api.endpoints import ENDPOINTS
from baseballpy.sources.mlb_api.generic import (
    HYDRATE_MARKER,
    HYDRATE_PARSE_REV,
    PARSE_REV_KEY,
    VIA_HYDRATE,
    VIA_KEY,
)


def main() -> int:
    """Count the stale hydrate chunks per dataset (nothing is written)."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true", help="check the sha256 of the raw pages")
    verify = parser.parse_args().verify
    catalog.register_all()
    lake = LakeConfig()
    raw = RawStore(lake)
    total_chunks = total_rows = 0
    print(f"{'dataset':45} {'stale':>6} {'rows':>10} {'no raw':>7} {'bad sha':>8} {'other':>7}")
    for ep in ENDPOINTS:
        if not (ep.paginated and ep.path == "v1/stats") or ep.unsupported:
            continue
        spec = get_dataset("mlb_api", ep.name)
        chunks = lake.dataset_manifest("mlb_api", ep.name).chunks()
        stale = rows = no_raw = bad = other = 0
        for key, entry in chunks.items():
            season = entry.get("season")
            ident = key.rsplit("/", 1)[-1]
            via = entry.get(VIA_KEY)
            p0 = f"{ident}{HYDRATE_MARKER}p0.json"
            if via is None:
                is_hydrate = raw.exists("mlb_api", ep.name, p0, season) and not raw.exists(
                    "mlb_api", ep.name, f"{ident}.p0.json", season
                )
            else:
                is_hydrate = via == VIA_HYDRATE
            if not is_hydrate:
                other += 1
                continue
            if entry.get(PARSE_REV_KEY) == HYDRATE_PARSE_REV and schema_matches(spec, entry):
                continue
            if not raw.exists("mlb_api", ep.name, p0, season):
                no_raw += 1
                continue
            if verify:
                n = 0
                while raw.exists("mlb_api", ep.name, f"{ident}{HYDRATE_MARKER}p{n}.json", season):
                    n += 1
                if not all(
                    raw.verify("mlb_api", ep.name, f"{ident}{HYDRATE_MARKER}p{i}.json", season)
                    for i in range(n)
                ):
                    bad += 1
                    continue
            stale += 1
            rows += int(entry.get("records_count") or 0)
        if stale or no_raw or bad:
            print(f"{ep.name:45} {stale:6} {rows:10,} {no_raw:7} {bad:8} {other:7}")
        total_chunks += stale
        total_rows += rows
    print(f"{'TOTAL':45} {total_chunks:6} {total_rows:10,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
