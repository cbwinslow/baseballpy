"""Probe every GitHub-hosted dataset family live and record the evidence in docs/endpoint_probe.json.

Usage::

    uv run python scripts/probe_endpoints.py [--out docs/endpoint_probe.json] [--seasons 1950 2023 2025]

For Retrosheet, Chadwick and Lahman each registered dataset is exercised with the smallest realistic
request: the pinned git tree is fetched, one representative file per dataset is downloaded through
the shared ``HttpClient`` and its header row is recorded. Anything that does not answer 200 is
recorded as ``unsupported`` with the HTTP status (never silently omitted). MLB Stats API and Savant
probes belong to their own coverage sections.
"""

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.github_tree import fetch_tree
from baseballpy.core.http import HttpClient, HttpStatusError, TransportError
from baseballpy.core.sources_lock import get_source_ref
from baseballpy.sources.retrosheet.tree import classify


def _probe(http: HttpClient, url: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = http.get_sync(url, allow=(200, 404))
    except (HttpStatusError, TransportError) as exc:
        return {"status": "unsupported", "error": str(exc), "url": url}
    elapsed = round(time.perf_counter() - started, 2)
    if result.status != 200:
        return {"status": "unsupported", "http_status": result.status, "url": url}
    first = result.content.split(b"\n", 1)[0].decode("utf-8-sig", errors="replace").strip()
    return {
        "status": "ok",
        "http_status": 200,
        "bytes": len(result.content),
        "elapsed_seconds": elapsed,
        "first_line": first[:300],
        "url": url,
    }


def probe_chadwick(http: HttpClient, config: LakeConfig) -> dict[str, Any]:
    """One file per Chadwick dataset."""
    ref = get_source_ref("chadwick_register")
    tree = {e.path for e in fetch_tree(ref, config, http)}
    out: dict[str, Any] = {"ref": ref.ref}
    for dataset, path in (
        ("register", "data/people-0.csv"),
        ("register_names", "data/names.csv"),
        ("register_links", "data/links.csv"),
        ("register_countries", "data/countries.csv"),
    ):
        out[dataset] = (
            _probe(http, ref.raw_url(path))
            if path in tree
            else {"status": "unsupported", "error": f"{path} not in the git tree"}
        )
    return out


def probe_lahman(http: HttpClient, config: LakeConfig) -> dict[str, Any]:
    """Every Lahman table."""
    from baseballpy.sources.lahman.schema import LahmanTable

    ref = get_source_ref("lahman")
    out: dict[str, Any] = {"ref": ref.ref, "repo": ref.repo}
    for table in LahmanTable:
        out[table.value] = _probe(http, ref.raw_url(f"data/{table.value}.csv"))
    return out


def probe_retrosheet(http: HttpClient, config: LakeConfig, seasons: list[int]) -> dict[str, Any]:
    """One file of every kind for the sample seasons, plus every reference/postseason file."""
    ref = get_source_ref("retrosheet")
    tree = classify(fetch_tree(ref, config, http))
    out: dict[str, Any] = {
        "ref": ref.ref,
        "seasons_in_tree": [tree.seasons()[0], tree.seasons()[-1]],
    }
    kinds: dict[str, Any] = {}
    for year in seasons:
        by_kind: dict[str, Any] = {}
        for kind in sorted({f.kind for f in tree.season_files(year)}):
            sample = min(
                (f for f in tree.season_files(year) if f.kind == kind), key=lambda f: f.size
            )
            by_kind[kind] = {"file": sample.path, **_probe(http, ref.raw_url(sample.path))}
        kinds[str(year)] = by_kind
    out["season_files"] = kinds
    out["reference"] = {f.name: _probe(http, ref.raw_url(f.path)) for f in tree.reference}
    out["postseason_gamelogs"] = {
        f.name: _probe(http, ref.raw_url(f.path)) for f in tree.postseason_gamelogs
    }
    out["uncovered_files"] = tree.uncovered
    return out


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("docs/endpoint_probe.json"))
    parser.add_argument("--seasons", type=int, nargs="*", default=[1950, 2023, 2025])
    args = parser.parse_args()

    config = LakeConfig()
    http = HttpClient(RateLimitConfig())
    try:
        existing: dict[str, Any] = {}
        if args.out.exists():
            existing = json.loads(args.out.read_text(encoding="utf-8"))
        existing.update(
            {
                "generated": date.today().isoformat(),
                "chadwick": probe_chadwick(http, config),
                "lahman": probe_lahman(http, config),
                "retrosheet": probe_retrosheet(http, config, args.seasons),
            }
        )
    finally:
        http.close()
    args.out.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    bad = [
        f"{source}.{name}"
        for source in ("chadwick", "lahman")
        for name, value in existing[source].items()
        if isinstance(value, dict) and value.get("status") == "unsupported"
    ]
    print(f"wrote {args.out}; unsupported: {bad or 'none'}", file=sys.stderr)
    if re.search("unsupported", json.dumps(existing["retrosheet"])):
        print("retrosheet has unsupported entries; see the file", file=sys.stderr)


if __name__ == "__main__":
    main()
