"""Save library documentation (Context7 extracts) into ``docs/references/``.

Context7's REST API needs no key, returns at most about 500 KB per request and ignores paging, so
each library is fetched once without a topic and once per listed topic; the result is an excerpt,
never the complete manual. Complete copies are shallow clones of the projects' own documentation
(see ``docs/references/README.md`` and ``scripts/clone_reference_docs.sh``).

    uv run python scripts/fetch_reference_docs.py [--only SLUG ...]
"""

import argparse
import datetime as dt
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://context7.com/api/v1"
OUT = Path(__file__).resolve().parent.parent / "docs" / "references"
TOKENS = 200_000  # per request; the service caps a response at about 500 KB

#: slug -> (Context7 library id, topics fetched in addition to the generic extract)
LIBRARIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "dlt": (
        "/websites/dlthub",
        (
            "rest_api source",
            "schema contracts and schema evolution",
            "incremental loading and state",
            "filesystem destination parquet",
            "duckdb destination",
            "arrow and polars sources",
            "nested data and child tables",
            "write dispositions merge",
        ),
    ),
    "polars": ("/pola-rs/polars", ("lazy scan_parquet", "datatypes", "io parquet")),
    "duckdb": (
        "/duckdb/duckdb-web",
        ("parquet", "create view", "python api", "httpfs and read_parquet hive partitioning"),
    ),
    "pyarrow": (
        "/apache/arrow",
        ("pyarrow schema and types", "pyarrow parquet", "pyarrow dataset", "record batch reader"),
    ),
    "narwhals": ("/narwhals-dev/narwhals", ()),
    "msgspec": ("/msgspec/msgspec", ()),
    "httpx": ("/encode/httpx", ("http2", "async client", "timeouts and limits")),
    "pydantic": ("/pydantic/pydantic", ("validation", "settings")),
    "pydantic-settings": ("/pydantic/pydantic-settings", ()),
    "tenacity": ("/jd/tenacity", ()),
    "aiolimiter": ("/mjpieters/aiolimiter", ()),
    "rich": ("/textualize/rich", ("tables",)),
    "click": ("/pallets/click", ()),
    "respx": ("/lundberg/respx", ()),
    "hypothesis": ("/hypothesisworks/hypothesis", ()),
    "pytest": ("/pytest-dev/pytest", ()),
    "pybaseball": ("/jldbc/pybaseball", ()),
    "baseballr": ("/llmstxt/billpetti_github_io_baseballr_llms_txt", ()),
    "mlb-statsapi": ("/toddrob99/mlb-statsapi", ()),
    "python-mlb-statsapi": ("/zero-sum-seattle/python-mlb-statsapi", ()),
    "mlb-stats-api-openapi": (
        "/openapi/raw_githubusercontent_saiemgilani_sdv-swagger_main_mlb-stats-api_openapi_yaml",
        (),
    ),
}


def fetch(library_id: str, topic: str | None) -> str:
    """One Context7 response (text) for a library, optionally narrowed to a topic."""
    query = {"type": "txt", "tokens": str(TOKENS)}
    if topic:
        query["topic"] = topic
    url = f"{BASE}{library_id}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(  # noqa: S310  (fixed https host)
        url, headers={"User-Agent": "baseballpy-reference-docs"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        return response.read().decode("utf-8")


def main() -> int:
    """Fetch every library (or the ones named with ``--only``); exit 1 when any request failed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    today = dt.datetime.now(dt.UTC).date().isoformat()
    failed = 0
    for slug, (library_id, topics) in LIBRARIES.items():
        if args.only and slug not in args.only:
            continue
        parts: list[str] = []
        seen: set[str] = set()
        for topic in (None, *topics):
            try:
                text = fetch(library_id, topic)
            except OSError as exc:
                print(f"{slug} [{topic}]: FAILED {exc}", file=sys.stderr)
                failed += 1
                continue
            if text in seen or not text.strip():
                continue
            seen.add(text)
            parts.append(f"<!-- topic: {topic or 'generic extract'} -->\n{text}")
            time.sleep(1.0)
        header = (
            f"# {slug}: documentation excerpt\n\n"
            f"- Source: Context7 `{library_id}` (https://context7.com{library_id})\n"
            f"- Fetched: {today}; excerpt only (the service caps a response at about 500 KB), not the "
            "complete manual. Upstream licences apply; see the upstream repository.\n\n"
        )
        (OUT / f"{slug}.txt").write_text(header + "\n\n".join(parts), encoding="utf-8")
        print(f"{slug}: {len(parts)} part(s), {sum(map(len, parts)) // 1024} KB")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
