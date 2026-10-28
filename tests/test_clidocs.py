"""``docs/CLI.md`` is generated from the click tree and must not be stale."""

from pathlib import Path

import click

from baseballpy.cli import main
from baseballpy.clidocs import CLI_DOC_NAME, generate_cli_doc, render_cli_docs

DOCS = Path(__file__).parent.parent / "docs"


def test_committed_cli_doc_is_not_stale() -> None:
    assert generate_cli_doc(main, DOCS, write=False) is False, (
        "run `baseballpy docs generate` and commit docs/CLI.md"
    )


def test_every_command_has_a_section() -> None:
    text = render_cli_docs(main)

    def paths(cmd: click.Command, prefix: str) -> list[str]:
        found = [prefix]
        if isinstance(cmd, click.Group):
            for name, child in cmd.commands.items():
                found += paths(child, f"{prefix} {name}")
        return found

    for path in paths(main, "baseballpy"):
        assert f"## `{path}`" in text, path


def test_render_is_deterministic_and_generate_writes(tmp_path: Path) -> None:
    assert render_cli_docs(main) == render_cli_docs(main)
    assert generate_cli_doc(main, tmp_path) is True
    assert (tmp_path / CLI_DOC_NAME).read_text(encoding="utf-8") == render_cli_docs(main)
    assert generate_cli_doc(main, tmp_path) is False
