"""Offline repair (ADR 130): parse stale hydrate stat-pool chunks again from their stored raw pages.

Usage: ``BASEBALLPY_HOME=<lake> uv run python scripts/hydrate_reparse.py [-d DATASET ...] [--force IDENT ...]``.
Never makes an HTTP request and never touches raw files or chunks the direct route filled. Each
chunk is rebuilt only when it is stale, its raw pages pass their checksum and the rebuilt row count
equals the stored one (``--force`` skips the stale test for the named chunk ids).
"""

from __future__ import annotations

import argparse
import logging

from baseballpy.core.config import LakeConfig
from baseballpy.sources import catalog
from baseballpy.sources.mlb_api.api import MlbApiSource
from baseballpy.sources.mlb_api.endpoints import ENDPOINTS, requests_for


def main() -> int:
    """Rebuild every stale hydrate chunk of the chosen stat pools from raw; print counts."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d", "--dataset", action="append", help="dataset name (default: all pools)"
    )
    parser.add_argument("--force", action="append", default=[], help="chunk id to rebuild anyway")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    catalog.register_all()
    source = MlbApiSource(cache_config=LakeConfig())
    extractor = source.endpoints
    sports = source.all_sport_ids()
    for ep in ENDPOINTS:
        if not (ep.paginated and ep.path == "v1/stats") or ep.unsupported:
            continue
        if args.dataset and ep.name not in args.dataset:
            continue
        chunks = extractor.cache_config.dataset_manifest("mlb_api", ep.name).chunks()
        seasons = sorted({int(e["season"]) for e in chunks.values() if e.get("season") is not None})
        rebuilt = rows = 0
        for season in seasons:
            ctx = source._context(season, sports)  # noqa: SLF001
            for request in requests_for(ep, ctx):
                table = extractor._rebuild_stale_hydrate(  # noqa: SLF001
                    ep, request, force=request.ident in args.force
                )
                if table is not None:
                    rebuilt += 1
                    rows += table.num_rows
        print(f"{ep.name:45} rebuilt {rebuilt:5} chunks, {rows:10,} rows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
