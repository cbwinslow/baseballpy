"""Build ``docs/columns/<source>.json`` from provider metadata (never from invention).

Usage::

    uv run python scripts/build_column_descriptions.py [mlb_api] [statcast]

Sources of truth, in order (OpenSpec change ``column-descriptions-from-provider-metadata``):

* MLB Stats API: ``/v1/baseballStats`` (label, groups, counting flag per statistic) and the code
  lists (``gameTypes``, ``pitchTypes``, ``eventTypes`` ...), plus short *authored* descriptions for
  structural columns (``*_id``, ``*_link``, ``*_name`` ...) flagged ``authored``.
* Statcast: the provider's own page ``https://baseballsavant.mlb.com/csv-docs`` (one card per
  pitch CSV column).

The output is deterministic and committed; ``baseballpy docs generate`` merges it.
"""

import html
import json
import re
import sys
from pathlib import Path
from typing import Any

from baseballpy.core.config import RateLimitConfig
from baseballpy.core.datasets import DATASETS
from baseballpy.core.http import HttpClient
from baseballpy.core.schema_tools import snake
from baseballpy.sources import catalog

OUT = Path("docs/columns")
MLB = "https://statsapi.mlb.com/api/v1"
CSV_DOCS = "https://baseballsavant.mlb.com/csv-docs"
_CARD = re.compile(
    r'<div id="docs-(?P<col>[^"]+)" class="savant-docs-card">.*?<p>(?P<text>.*?)</p>', re.DOTALL
)
_TAG = re.compile(r"<[^>]+>")


def clean(text: str) -> str:
    """Strip tags, unescape entities and collapse whitespace."""
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", text))).strip()


def csv_docs(content: str) -> dict[str, str]:
    """``{column: text}`` from the Savant CSV documentation page."""
    return {m.group("col"): clean(m.group("text")) for m in _CARD.finditer(content)}


def columns_of(source: str) -> list[tuple[str, str]]:
    """Every ``(dataset, column)`` of a source in the registry."""
    catalog.register_all()
    return [
        (spec.name, field.name)
        for spec in DATASETS.values()
        if spec.source == source
        for field in spec.schema
        if field.name != "_extras"
    ]


def build_mlb(http: HttpClient) -> dict[str, Any]:
    """MLB descriptions: provider statistic definitions and code lists, plus authored structure."""
    sources = {
        "mlb_baseball_stats": f"{MLB}/baseballStats",
        "mlb_game_types": f"{MLB}/gameTypes",
        "mlb_pitch_types": f"{MLB}/pitchTypes",
        "mlb_positions": f"{MLB}/positions",
        "mlb_situation_codes": f"{MLB}/situationCodes",
        "mlb_stat_types": f"{MLB}/statTypes",
        "mlb_stat_groups": f"{MLB}/statGroups",
        "mlb_metrics": f"{MLB}/metrics",
    }
    star: dict[str, Any] = {}
    stats = http.get_sync(f"{MLB}/baseballStats").json()
    for item in stats:
        groups = ", ".join(g["displayName"] for g in item.get("statGroups", [])) or "any group"
        kind = "counting statistic" if item.get("isCounting") else "rate or derived statistic"
        label = item.get("label") or item["name"]
        lookup = f"; lookup parameter `{item['lookupParam']}`" if item.get("lookupParam") else ""
        star[snake("stat." + item["name"])] = {
            "text": f"{label}: {kind} ({groups}){lookup}.",
            "source": "mlb_baseball_stats",
        }
    game_types = http.get_sync(f"{MLB}/gameTypes").json()
    star["game_type"] = {
        "text": "Game type code: "
        + ", ".join(f"{g['id']} = {g['description']}" for g in game_types)
        + ".",
        "source": "mlb_game_types",
    }
    pitch_types = http.get_sync(f"{MLB}/pitchTypes").json()
    star["details_type_code"] = {
        "text": "Pitch type code: "
        + ", ".join(f"{p['code']} = {p['description']}" for p in pitch_types)
        + ".",
        "source": "mlb_pitch_types",
    }
    positions = http.get_sync(f"{MLB}/positions").json()
    star["position_abbreviation"] = {
        "text": "Position abbreviation: "
        + ", ".join(f"{p['abbrev']} = {p['fullName']}" for p in positions)
        + ".",
        "source": "mlb_positions",
    }
    star["stats_type_display_name"] = {
        "text": "Stat type of the response (a value of /v1/statTypes).",
        "source": "mlb_stat_types",
    }
    star["stats_group_display_name"] = {
        "text": "Stat group of the response (a value of /v1/statGroups).",
        "source": "mlb_stat_groups",
    }
    for column in sorted({c for _, c in columns_of("mlb_api")} - set(star)):
        text = structural(column)
        if text:
            star[column] = {"text": text, "authored": True}
    return {"_sources": sources, "*": star}


def structural(column: str) -> str | None:
    """Authored one-line meaning of ubiquitous structural columns (flagged ``authored``)."""
    for suffix, template in (
        ("_full_name", "Full name of the {x}."),
        ("_abbreviation", "Abbreviation of the {x}."),
        (
            "_link",
            "Relative MLB Stats API path of the {x} resource (prefix https://statsapi.mlb.com).",
        ),
        ("_id", "MLBAM identifier of the {x}."),
        ("_name", "Name of the {x}."),
        ("_code", "Code of the {x}."),
    ):
        if column.endswith(suffix) and len(column) > len(suffix):
            return template.format(x=column[: -len(suffix)].replace("_", " "))
    return None


def build_statcast(http: HttpClient) -> dict[str, Any]:
    """Statcast descriptions from the provider's pitch CSV documentation page."""
    page = http.get_sync(CSV_DOCS).content.decode("utf-8", "replace")
    docs = csv_docs(page)
    if not docs:
        raise SystemExit(f"no documentation cards found at {CSV_DOCS}; the page layout changed")
    pitch_columns = {c for d, c in columns_of("statcast") if d == "pitches"}
    entry = {
        col: {"text": docs[col], "source": "savant_csv_docs"}
        for col in sorted(pitch_columns)
        if col in docs
    }
    return {
        "_sources": {"savant_csv_docs": CSV_DOCS},
        "pitches": entry,
        "pitches_minors": entry,
    }


def main() -> int:
    """Write the requested sources (default: all)."""
    wanted = sys.argv[1:] or ["mlb_api", "statcast"]
    http = HttpClient(RateLimitConfig())
    OUT.mkdir(parents=True, exist_ok=True)
    builders = {"mlb_api": build_mlb, "statcast": build_statcast}
    for source in wanted:
        data = builders[source](http)
        (OUT / f"{source}.json").write_text(
            json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        described = sum(len(v) for k, v in data.items() if k != "_sources")
        print(f"{source}: {described} descriptions written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
