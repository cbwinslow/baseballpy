"""The quickstart opens with a "Start here" path whose commands are real (change quickstart-start-here)."""

import re
from pathlib import Path

from baseballpy.cli import main
from baseballpy.ingest import ADAPTERS
from baseballpy.sources.adapters import register_all_adapters

QUICKSTART = Path(__file__).resolve().parent.parent / "docs" / "QUICKSTART.md"
HEADING = "## Start here"


def _section() -> str:
    text = QUICKSTART.read_text(encoding="utf-8")
    assert HEADING in text, "docs/QUICKSTART.md has no Start here section"
    return text.split(HEADING, 1)[1].split("\n## ", 1)[0]


def test_the_start_here_section_is_first_and_has_five_steps_and_a_table() -> None:
    text = QUICKSTART.read_text(encoding="utf-8")
    first = re.search(r"^## ", text, re.M)
    assert first is not None and text[first.start() :].startswith(HEADING)
    section = _section()
    assert len(re.findall(r"^\d\. \*\*", section, re.M)) == 5
    for source in ("statcast", "retrosheet", "chadwick", "lahman", "mlb_api"):
        assert f"`{source}`" in section, f"no first command for {source}"


def test_the_start_here_commands_are_real() -> None:
    register_all_adapters()
    commands = re.findall(r"baseballpy ([a-z][a-z-]*)((?: [^\n`|]*)?)", _section())
    assert commands, "no baseballpy command in the section"
    for name, rest in commands:
        assert name in main.commands, f"`baseballpy {name}` is not a command"
        if name == "ingest":
            source = rest.split()[0] if rest.split() else ""
            assert source in ADAPTERS, f"`ingest {source}` is not a registered source"
