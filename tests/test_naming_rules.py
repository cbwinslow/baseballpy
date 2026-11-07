"""Names are predictable: sources, datasets, views, doc files and processed folders follow one rule."""

import re
from pathlib import Path

import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS
from baseballpy.layout_audit import LayoutKind, audit_layout
from baseballpy.sources.catalog import register_all

SNAKE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
#: the only sources whose views do not start with the source name
VIEW_PREFIX = {"mlb_api": "mlb"}
DOCS = Path(__file__).resolve().parent.parent / "docs" / "sources"


@pytest.fixture(scope="module", autouse=True)
def _registered() -> None:
    register_all()


def test_sources_and_datasets_are_lower_snake_case() -> None:
    bad = [
        (s.source, s.name)
        for s in DATASETS.values()
        if not (SNAKE.match(s.source) and SNAKE.match(s.name))
    ]
    assert bad == []


def test_views_follow_source_underscore_dataset_with_one_declared_exception() -> None:
    wrong = [
        (s.source, s.name, s.view)
        for s in DATASETS.values()
        if s.view != f"{VIEW_PREFIX.get(s.source, s.source)}_{s.name}"
    ]
    assert wrong == []
    views = [s.view for s in DATASETS.values()]
    assert len(views) == len(set(views)), "two datasets share a view name"


def test_every_source_has_a_doc_file_and_every_doc_file_has_a_source() -> None:
    sources = {s.source for s in DATASETS.values()}
    docs = {p.stem for p in DOCS.glob("*.md")}
    assert sources == docs


def test_a_processed_folder_no_dataset_owns_fails_the_layout_check() -> None:
    config = LakeConfig()
    (config.processed_root / "statcast" / "pitchez").mkdir(parents=True)
    (config.processed_root / "nosuchsource" / "x").mkdir(parents=True)
    findings = [f for f in audit_layout(config) if f.kind is LayoutKind.UNKNOWN_FOLDER]
    assert {(f.source, f.item) for f in findings} == {
        ("statcast", "pitchez/"),
        ("nosuchsource", "nosuchsource/"),
    }
    assert all(f.fails for f in findings)


def test_registered_folders_are_not_unknown() -> None:
    config = LakeConfig()
    (config.processed_root / "statcast" / "pitches").mkdir(parents=True)
    assert [f for f in audit_layout(config) if f.kind is LayoutKind.UNKNOWN_FOLDER] == []
