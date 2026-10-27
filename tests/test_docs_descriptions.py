"""Column descriptions: provenance, defaults, TODO marker, coverage and the ratchet."""

import json
from pathlib import Path

import pyarrow as pa

from baseballpy.core.datasets import DatasetSpec
from baseballpy.docsgen import (
    EXTRAS_TEXT,
    TODO,
    Described,
    description_coverage,
    load_descriptions,
    lookup,
    render_dataset,
    render_sources_block,
)

DOCS = Path(__file__).parent.parent / "docs"


def _write(tmp: Path, source: str, data: dict[str, object]) -> Path:
    path = tmp / "columns" / f"{source}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return tmp


def test_load_supports_strings_dicts_defaults_and_sources(tmp_path: Path) -> None:
    docs = _write(
        tmp_path,
        "mlb_api",
        {
            "_sources": {"api": "https://example.test/stats"},
            "*": {"id": {"text": "Numeric id", "source": "api"}},
            "teams": {"name": "Club name", "abbr": {"text": "Abbreviation", "authored": True}},
        },
    )
    sources, table = load_descriptions(docs, "mlb_api")
    assert sources == {"api": "https://example.test/stats"}
    assert table["*"]["id"] == Described("Numeric id", "api", False)
    assert table["teams"]["name"] == Described("Club name", None, True)
    assert load_descriptions(tmp_path / "nowhere", "mlb_api") == ({}, {})


def test_dataset_entry_wins_over_the_source_default() -> None:
    table = {
        "*": {"id": Described("generic", "k")},
        "teams": {"id": Described("team id", "k")},
    }
    assert lookup(table, "teams", "id") == Described("team id", "k")
    assert lookup(table, "venues", "id") == Described("generic", "k")
    assert lookup(table, "venues", "nothing") is None
    assert lookup({}, "x", "_extras") == Described(EXTRAS_TEXT, None, True)


def _spec() -> DatasetSpec:
    schema = pa.schema(
        [
            pa.field("id", pa.int32()),
            pa.field("name", pa.string()),
            pa.field("_extras", pa.string()),
        ]
    )
    return DatasetSpec("mlb_api", "teams", "mlb_teams", schema, "none", ("id",), "Teams.", "x.md")


def test_render_marks_missing_cites_sources_and_escapes_pipes() -> None:
    table = {"teams": {"id": Described("Id | key", "api"), "name": Described("Name", None, True)}}
    block = render_dataset(_spec(), table)
    assert "| `id` | int32 | yes | — | Id / key (src: api) |" in block
    assert "| `name` | string | yes | — | Name (authored) |" in block
    assert f"| `_extras` | string | yes | — | {EXTRAS_TEXT} (authored) |" in block
    assert TODO in render_dataset(_spec(), {})


def test_sources_block_lists_every_cited_source() -> None:
    block = render_sources_block("mlb_api", {"b": "doc B", "a": "https://a.test"})
    assert block.index("`a`") < block.index("`b`") and "https://a.test" in block
    assert "No column descriptions" in render_sources_block("lahman", {})


def test_coverage_counts_defaults_and_extras(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from baseballpy.core import datasets

    monkeypatch.setattr(datasets, "DATASETS", {"mlb_api.teams": _spec()})
    monkeypatch.setattr("baseballpy.docsgen.DATASETS", {"mlb_api.teams": _spec()})
    monkeypatch.setattr("baseballpy.docsgen.catalog.register_all", lambda: {})
    docs = _write(tmp_path, "mlb_api", {"*": {"id": "Numeric id"}, "teams": {"name": "Name"}})
    assert description_coverage(docs) == {"mlb_api": (3, 3)}
    assert description_coverage(tmp_path / "nowhere") == {"mlb_api": (1, 3)}


def test_described_columns_never_drop_below_the_committed_baseline() -> None:
    """Ratchet: raise ``docs/columns/coverage_baseline.json`` with ``docs coverage --write-baseline``."""
    path = DOCS / "columns" / "coverage_baseline.json"
    baseline: dict[str, int] = json.loads(path.read_text("utf-8")) if path.exists() else {}
    coverage = description_coverage(DOCS)
    for source, minimum in baseline.items():
        described, total = coverage[source]
        assert described >= minimum, f"{source}: {described}/{total} described, baseline {minimum}"
