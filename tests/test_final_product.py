"""The constitution defines the final product per source and cannot drift from the registry (final-product-definition)."""

import re
from pathlib import Path

from baseballpy.cli import main
from baseballpy.core.datasets import SOURCES
from baseballpy.ingest import ADAPTERS
from baseballpy.sources.adapters import register_all_adapters

PROJECT = Path(__file__).resolve().parent.parent / "openspec" / "project.md"
HEADING = "## The Final Product"


def _section() -> str:
    text = PROJECT.read_text(encoding="utf-8")
    assert HEADING in text, "openspec/project.md has no 'The Final Product' section"
    return text.split(HEADING, 1)[1].split("\n## ", 1)[0]


def test_the_constitution_has_one_row_per_registered_source() -> None:
    section = _section()
    rows = re.findall(r"^\| ((?:`[a-z_]+`(?:, )?)+) \|", section, re.M)
    listed = {name for row in rows for name in re.findall(r"`([a-z_]+)`", row)}
    missing = set(SOURCES) - listed
    assert not missing, f"sources without a row in The Final Product: {sorted(missing)}"
    for phrase in ("Target layout", "seg-NNNN.parquet", "Definition of done", "never deleted"):
        assert phrase in section, f"the section lacks {phrase!r}"


def test_every_first_command_names_a_registered_source() -> None:
    register_all_adapters()
    commands = re.findall(r"`baseballpy ([a-z][a-z-]*)((?: [^`]*)?)`", _section())
    assert commands, "no first command in the table"
    for name, rest in commands:
        assert name in main.commands, f"`baseballpy {name}` is not a command"
        if name == "ingest":
            source = rest.split()[0] if rest.split() else ""
            if source.startswith("<"):
                continue  # a placeholder such as <source>, not a real command line
            assert source in ADAPTERS, f"`ingest {source}` is not a registered source"
