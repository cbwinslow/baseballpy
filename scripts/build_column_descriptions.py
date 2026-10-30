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

import retro_glfields

from baseballpy.core.config import RateLimitConfig
from baseballpy.core.datasets import DATASETS
from baseballpy.core.http import HttpClient
from baseballpy.core.schema_tools import snake
from baseballpy.core.sources_lock import get_source_ref
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
    # Response keys are the provider's own ``lookupParam`` (battingAverage -> avg): use it as
    # an alias only when exactly one statistic claims it, never by similarity.
    claims: dict[str, list[dict[str, Any]]] = {}
    for item in stats:
        if item.get("lookupParam"):
            claims.setdefault(snake("stat." + item["lookupParam"]), []).append(item)
    for column, items in claims.items():
        if len(items) == 1 and column not in star:
            star[column] = star[snake("stat." + items[0]["name"])]
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


GLOSSARY = "https://www.mlb.com/glossary/statcast/"
#: leaderboard columns whose name is exactly the metric's own abbreviation, with the MLB glossary
#: page that defines the metric (the provider's text; a column not listed stays undescribed)
GLOSSARY_COLUMNS = {
    "xwoba": "expected-woba",
    "xba": "expected-batting-average",
    "xslg": "expected-slugging-percentage",
    "xera": "expected-era",
    "hard_hit_percent": "hard-hit-rate",
    "sprint_speed": "sprint-speed",
    "spin_rate": "spin-rate",
    "arm_strength": "arm-strength",
    "attack_angle": "attack-angle",
    "attack_direction": "attack-direction",
    "swing_length": "swing-length",
    "swing_tilt": "swing-path-tilt",
    "oaa": "outs-above-average",
    "bolts": "bolt",
    "anglesweetspotpercent": "sweet-spot",
    "squared_up_rate": "squared-up",
    "barrels": "barrel",
}
_GLOSSARY_PARAGRAPH = re.compile(r"\\u003cp\\u003e(.*?)\\u003c/p")
_FIRST_SENTENCE = re.compile(r"^.*?[.!?](?=\s+[A-Z\"']|$)", re.DOTALL)


def glossary_definition(page: str) -> str:
    """First sentence of the first paragraph of an MLB glossary page (its JSON-embedded body)."""
    backslash = chr(92)
    for raw in _GLOSSARY_PARAGRAPH.findall(page):
        text = raw.replace(backslash + "u003c", "<").replace(backslash + "u003e", ">")
        text = text.replace(backslash + "u0026", "&").replace(backslash + '"', '"')
        text = clean(text)
        if len(text) > 30:
            match = _FIRST_SENTENCE.match(text)
            return match.group(0) if match else text
    return ""


def build_statcast(http: HttpClient) -> dict[str, Any]:
    """Statcast descriptions: the pitch CSV page, plus the MLB glossary for named leaderboard metrics."""
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
    sources = {"savant_csv_docs": CSV_DOCS}
    star: dict[str, Any] = {}
    for column, term in sorted(GLOSSARY_COLUMNS.items()):
        url = f"{GLOSSARY}{term}"
        text = glossary_definition(http.get_sync(url).content.decode("utf-8", "replace"))
        if not text:
            raise SystemExit(f"no definition found at {url}; the page layout changed")
        key = f"mlb_glossary_{term.replace('-', '_')}"
        sources[key] = url
        star[column] = {"text": text, "source": key}
    return {"_sources": sources, "*": star, "pitches": entry, "pitches_minors": entry}


#: the data dictionary at the PINNED commit of the mirror (never a moving branch), so every
#: description cites exactly the text it was built from
LAHMAN_README = f"{get_source_ref('lahman').raw_base()}/data/readme2025.txt"
CHADWICK_README = "https://raw.githubusercontent.com/chadwickbureau/register/master/README.md"
_LAHMAN_ALIASES = {"teamfranchises": "teamsfranchises"}
_COLUMN_LINE = re.compile(r"^(\w+)\s{2,}(\S.*)$")


def lahman_sections(text: str) -> dict[str, dict[str, str]]:
    """``{table heading (compact, lower): {column: text}}`` from the SABR readme."""
    out: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    last = ""
    for line in text.splitlines():
        if line.rstrip().endswith(" TABLE") and line.isupper():
            key = line.replace(" TABLE", "").replace(" ", "").lower()
            current = out.setdefault(_LAHMAN_ALIASES.get(key, key), {})
            last = ""
        elif current is None or line.startswith("---") or not line.strip():
            last = "" if not line.strip() else last
        elif (m := _COLUMN_LINE.match(line)) and not line.startswith(" "):
            last = m.group(1)
            current[last] = m.group(2).strip()
        elif last and line.startswith(" "):
            current[last] += " " + line.strip()
    return out


def build_lahman(http: HttpClient) -> dict[str, Any]:
    """Lahman descriptions: the SABR data dictionary (readme) per table and column."""
    sections = lahman_sections(http.get_sync(LAHMAN_README).content.decode("utf-8", "replace"))
    out: dict[str, Any] = {"_sources": {"lahman_readme": LAHMAN_README}}
    for dataset, column in columns_of("lahman"):
        found = sections.get(dataset.lower(), {})
        match = next((v for k, v in found.items() if k.lower() == column.lower()), None)
        if match:
            out.setdefault(dataset, {})[column] = {"text": match, "source": "lahman_readme"}
    return out


_CHADWICK_KEYS = {
    "key_uuid": "The primary key. This is guaranteed not to be re-used to label a different identity.",
    "key_person": "The first eight (hex) digits of the key_uuid; unique at any given time, but over time the same short key may be re-used for a different identity.",
    "key_retro": "The person's Retrosheet identifier.",
    "key_mlbam": "The person's identifier at MLBAM.",
    "key_bbref": "The person's identifier on Major League pages on baseball-reference.com.",
    "key_bbref_minors": "The person's identifier on minor league pages on baseball-reference.com.",
    "key_fangraphs": "The person's identifier on fangraphs.com.",
    "key_npb": "The person's identifier on the NPB official site, npb.or.jp.",
    "key_sr_nfl": "The person's identifier on pro-football-reference.com.",
    "key_sr_nba": "The person's identifier on basketball-reference.com.",
    "key_sr_nhl": "The person's identifier on hockey-reference.com.",
    "key_wikidata": "The person's identifier on wikidata.org.",
}
_CHADWICK_SPANS = {
    "pro": "professional leagues overall",
    "mlb": "Major League Baseball",
    "col": "intercollegiate play",
}


def build_chadwick(http: HttpClient) -> dict[str, Any]:
    """Chadwick descriptions from the register README (identifier list, year spans, names)."""
    page = http.get_sync(CHADWICK_README).content.decode("utf-8", "replace")
    star: dict[str, Any] = {}
    for column, text in _CHADWICK_KEYS.items():
        if f"`{column}`" not in page:
            raise SystemExit(f"{column} no longer documented in {CHADWICK_README}")
        star[column] = {"text": text, "source": "chadwick_readme"}
    for prefix, scope in _CHADWICK_SPANS.items():
        for role in ("played", "managed", "umpired"):
            for end in ("first", "last"):
                star[f"{prefix}_{role}_{end}"] = {
                    "text": f"{end.capitalize()} year spanned as {role[:-2]}er in {scope} "
                    "(README: year spans for playing, managing and umpiring; may be incomplete).",
                    "source": "chadwick_readme",
                }
    for column in (
        "name_last",
        "name_first",
        "name_given",
        "birth_year",
        "birth_month",
        "birth_day",
        "death_year",
        "death_month",
        "death_day",
    ):
        star[column] = {
            "text": "Basic name component or date of birth/death (README: People files).",
            "source": "chadwick_readme",
        }
    if "tsncards" not in page or "findagrave" not in page:
        raise SystemExit(f"links sources no longer documented in {CHADWICK_README}")
    if "alias" not in page or "legal names" not in page:
        raise SystemExit(f"names kinds no longer documented in {CHADWICK_README}")
    links = {
        "source": "The external system the link comes from (README: the public version publishes "
        "tsncards and findagrave).",
        "value": "The person's identifier in that system (README: the Sporting News contract card "
        "number for tsncards, a memorial ID for findagrave).",
    }
    names = {
        "altname_type": "Kind of alternate name (README: aliases/assumed names, legal names, birth "
        "names, or anglicizations/abbreviations of names).",
    }
    # countries.csv is not documented in the README; its columns are the code systems they name
    countries = {
        "key_iso_alpha2": ("Two-letter country code of ISO 3166-1 (alpha-2).", "iso_3166_1"),
        "key_iso_alpha3": ("Three-letter country code of ISO 3166-1 (alpha-3).", "iso_3166_1"),
        "key_ioc": ("Country code of the International Olympic Committee.", "ioc_codes"),
        "key_fifa": ("Country code used by FIFA.", "fifa_codes"),
    }
    out: dict[str, Any] = {
        "_sources": {
            "chadwick_readme": CHADWICK_README,
            "iso_3166_1": "https://en.wikipedia.org/wiki/ISO_3166-1",
            "ioc_codes": "https://en.wikipedia.org/wiki/List_of_IOC_country_codes",
            "fifa_codes": "https://en.wikipedia.org/wiki/List_of_FIFA_country_codes",
        },
        "*": star,
        "register_links": {
            c: {"text": text, "source": "chadwick_readme"} for c, text in links.items()
        },
        "register_names": {
            c: {"text": text, "source": "chadwick_readme"} for c, text in names.items()
        },
        "register_countries": {
            c: {"text": text, "source": source} for c, (text, source) in countries.items()
        },
    }
    return out


CHADWICK_DOCS = "https://raw.githubusercontent.com/chadwickbureau/chadwick/b0002b6a0c98f800f899635f5de17ebfcc976333/doc/"
#: Chadwick tool documents that define the field names Retrosheet datasets carry (cwevent, ...)
RETRO_DOCS = {
    "cwevent": ("events", "events_postseason", "events_deduced"),
    "cwdaily": ("daily_splits",),
    "cwsub": ("substitutions",),
}
# a table row: number, description (it may wrap onto several lines), then the header in backticks
_RST_ROW = re.compile(
    r"^\s+\* - \S+\n\s+- (?P<text>(?:(?!\n\s+\* - ).)+?)\n\s+- ``(?P<col>[A-Za-z0-9_]+)``",
    re.MULTILINE | re.DOTALL,
)
_RST_REF = re.compile(r":ref:`([^<`]*?)\s*<[^>]*>`", re.DOTALL)
# the cwdaily fielding table: one row per position, one cell per statistic ("71 ``F_P_G``")
_RST_SUFFIX = re.compile(r"^- ``(?P<suffix>[A-Z]+)``: (?P<text>[^;.]+)[;.]", re.MULTILINE)
_RST_POSITION_ROW = re.compile(
    r"^\s+\* - (?P<position>[A-Za-z ]+)\n(?P<cells>(?:\s+- \d+ ``[A-Z0-9_]+``\n?)+)", re.MULTILINE
)
_RST_CELL = re.compile(r"``(?P<col>F_(?P<pos>[A-Z0-9]+)_(?P<suffix>[A-Z]+))``")


def rst_fields(text: str) -> dict[str, str]:
    """``{FIELD_NAME: description}`` from the field tables of a Chadwick tool document."""
    out: dict[str, str] = {}
    for m in _RST_ROW.finditer(text):
        description = " ".join(_RST_REF.sub(r"\1", m.group("text")).split())
        out.setdefault(m.group("col"), description)
    meanings = {m.group("suffix"): m.group("text").strip() for m in _RST_SUFFIX.finditer(text)}
    for row in _RST_POSITION_ROW.finditer(text):
        position = row.group("position").strip().lower()
        for cell in _RST_CELL.finditer(row.group("cells")):
            if meaning := meanings.get(cell.group("suffix")):
                out.setdefault(cell.group("col"), f"{meaning[0].upper()}{meaning[1:]} ({position})")
    return out


def build_retrosheet(http: HttpClient) -> dict[str, Any]:
    """Retrosheet descriptions from the Chadwick tool documents (retrosheet.org was unreachable)."""
    out: dict[str, Any] = {"_sources": {}}
    for doc, datasets in RETRO_DOCS.items():
        url = f"{CHADWICK_DOCS}{doc}.rst"
        fields = rst_fields(http.get_sync(url).content.decode("utf-8", "replace"))
        if not fields:
            raise SystemExit(f"no field table found in {url}")
        key = f"chadwick_{doc}"
        out["_sources"][key] = url
        for dataset in datasets:
            names = {c for d, c in columns_of("retrosheet") if d == dataset}
            out[dataset] = {
                c: {"text": fields[c], "source": key} for c in sorted(names) if c in fields
            }
    games = build_gamelogs(http)
    out["_sources"].update(games.pop("_sources"))
    out.update(games)
    return out


GLFIELDS_URL = "https://raw.githubusercontent.com/maxtoki/baseball_R/3117ffda2b8d33397095a74b3ab27b4bbb2df2a5/data/glfields.txt"
GLFIELDS_NOTE = (
    "Retrosheet game-log field guide (glfields.txt), read from the copy in the book companion "
    f"repository maxtoki/baseball_R because retrosheet.org was unreachable: {GLFIELDS_URL}"
)
GAMELOG_DATASETS = ("gamelogs", "gamelogs_postseason")


def build_gamelogs(http: HttpClient) -> dict[str, Any]:
    """Game-log columns from the field guide; field ``n`` is the ``n``-th schema column."""
    fields = retro_glfields.describe(
        retro_glfields.parse(http.get_sync(GLFIELDS_URL).content.decode("utf-8", "replace"))
    )
    out: dict[str, Any] = {"_sources": {"retrosheet_glfields": GLFIELDS_NOTE}}
    catalog.register_all()
    for dataset in GAMELOG_DATASETS:
        names = [c for d, c in columns_of("retrosheet") if d == dataset and c != "_extras"]
        if len(names) != len(fields):
            raise SystemExit(f"{dataset}: {len(names)} columns but {len(fields)} documented fields")
        out[dataset] = {
            name: {"text": fields[i], "source": "retrosheet_glfields"}
            for i, name in enumerate(names, start=1)
        }
    return out


def main() -> int:
    """Write the requested sources (default: all)."""
    wanted = sys.argv[1:] or ["mlb_api", "statcast", "lahman", "chadwick", "retrosheet"]
    http = HttpClient(RateLimitConfig())
    OUT.mkdir(parents=True, exist_ok=True)
    builders = {
        "mlb_api": build_mlb,
        "statcast": build_statcast,
        "lahman": build_lahman,
        "chadwick": build_chadwick,
        "retrosheet": build_retrosheet,
    }
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
