"""The lake must open on any OS: portable names, case-insensitive uniqueness, relocatable manifests."""

import json
import re
from pathlib import Path

import pyarrow as pa
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS, SOURCES, DatasetSpec
from baseballpy.core.stores import (
    MAX_CHUNK_ID_LENGTH,
    ProcessedStore,
    RawStore,
    portable_name_problem,
)
from baseballpy.sources import catalog

_IDENT = re.compile(r"[a-z][a-z0-9_]*")


@pytest.mark.parametrize(
    "name",
    ["KXMLBGAME", "KXHIGHNY-25JUL21-T84.99", "2024-06-15", "events-KXWSAL-p00001.json", "a_b-c.d"],
)
def test_ordinary_names_are_portable(name: str) -> None:
    assert portable_name_problem(name) is None


@pytest.mark.parametrize(
    ("name", "why"),
    [
        ("", "empty"),
        ("a/b", "leave its directory"),
        ("a\\b", "leave its directory"),
        ("..", "leave its directory"),
        ("a:b", "forbids"),
        ("what?", "forbids"),
        ("a|b", "forbids"),
        ('say"hi"', "forbids"),
        ("tab\there", "forbids"),
        ("trailing.", "dot or a space"),
        ("trailing ", "dot or a space"),
        ("CON", "reserved"),
        ("nul.txt", "reserved"),
        ("Com3", "reserved"),
        ("x" * (MAX_CHUNK_ID_LENGTH + 1), "longer"),
    ],
)
def test_names_that_break_on_some_os_are_named_and_refused(name: str, why: str) -> None:
    problem = portable_name_problem(name)
    assert problem is not None and why in problem


def test_every_registered_name_is_lowercase_portable_and_unique_ignoring_case() -> None:
    catalog.register_all()
    assert all(_IDENT.fullmatch(s) for s in SOURCES)
    views: set[str] = set()
    keys: set[str] = set()
    for spec in DATASETS.values():
        for label, value in (("name", spec.name), ("view", spec.view)):
            assert _IDENT.fullmatch(value), (
                f"{spec.key}: {label} {value!r} is not lowercase snake_case"
            )
            assert portable_name_problem(value) is None, (spec.key, value)
        assert len(spec.name) <= 80 and len(spec.view) <= 80, spec.key
        assert spec.key.casefold() not in keys, (
            f"{spec.key} clashes with another name ignoring case"
        )
        keys.add(spec.key.casefold())
        assert spec.view.casefold() not in views, f"view {spec.view} is used twice"
        views.add(spec.view.casefold())


def _spec() -> DatasetSpec:
    return DatasetSpec(
        source="kalshi",
        name="markets",
        view="kalshi_markets",
        schema=pa.schema([("ticker", pa.string())]),
        partition="none",
        keys=("ticker",),
        description="test",
        endpoint_doc="sources/kalshi.md",
    )


def test_a_chunk_id_that_is_not_portable_is_refused_before_anything_is_written(
    tmp_path: Path,
) -> None:
    store = ProcessedStore(LakeConfig(base_dir=tmp_path))
    table = pa.table({"ticker": ["a"]})
    for bad in ("CON", "a:b", "x" * 200, "a/b"):
        with pytest.raises(ValueError, match="invalid chunk id"):
            store.put(_spec(), table, chunk_id=bad)
    with pytest.raises(ValueError, match="invalid chunk id"):
        RawStore(LakeConfig(base_dir=tmp_path)).put("kalshi", "markets", "a:b.json", b"{}")
    assert not list(tmp_path.rglob("*.parquet")) and not any(
        "a:b" in f.name for f in tmp_path.rglob("*")
    )


def test_two_chunks_that_differ_only_by_case_never_share_a_file(tmp_path: Path) -> None:
    store = ProcessedStore(LakeConfig(base_dir=tmp_path))
    table = pa.table({"ticker": ["a"]})
    store.put(_spec(), table, chunk_id="KXMLBGAME")
    with pytest.raises(ValueError, match="would share the file"):
        store.put(_spec(), table, chunk_id="kxmlbgame")


def test_manifests_hold_relative_names_so_a_lake_can_be_moved(tmp_path: Path) -> None:
    config = LakeConfig(base_dir=tmp_path)
    ProcessedStore(config).put(_spec(), pa.table({"ticker": ["a"]}), chunk_id="KXMLBGAME")
    RawStore(config).put("kalshi", "markets", "markets-KXMLBGAME-p00000.json", b"{}")
    manifests = list(tmp_path.rglob("_manifest.json"))
    assert len(manifests) == 2
    for path in manifests:
        text = path.read_text(encoding="utf-8")
        assert str(tmp_path) not in text and str(tmp_path).replace("\\", "/") not in text
        assert not re.search(r"[A-Za-z]:[\\/]|/home/|/Users/", text), path
        json.loads(text)
