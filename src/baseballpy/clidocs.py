"""Render ``docs/CLI.md`` from the click command tree, so the CLI reference cannot drift from the code.

The page is the ``--help`` text of every command, in command-tree order, at a fixed terminal width
(the output must not depend on the machine that generates it). ``baseballpy docs generate`` writes
it and ``--check`` / the docs tests fail when it is stale.
"""

from pathlib import Path

import click

CLI_DOC_NAME = "CLI.md"
HELP_WIDTH = 100

_HEADER = """# Command-line reference

Generated from the click help of `baseballpy` by `baseballpy docs generate`; do not edit by hand.
Every command and its options are listed below, one section per command.
"""


def _walk(command: click.Command, path: list[str], parent: click.Context | None) -> list[str]:
    ctx = click.Context(
        command,
        info_name=path[-1],
        parent=parent,
        terminal_width=HELP_WIDTH,
        max_content_width=HELP_WIDTH,
    )
    sections = [f"## `{' '.join(path)}`\n\n```text\n{command.get_help(ctx).rstrip()}\n```\n"]
    if isinstance(command, click.Group):
        for name in sorted(command.list_commands(ctx)):
            child = command.get_command(ctx, name)
            if child is not None and not child.hidden:
                sections += _walk(child, [*path, name], ctx)
    return sections


def render_cli_docs(root: click.Group, name: str = "baseballpy") -> str:
    """The full CLI reference page for ``root`` (a click group named ``name``)."""
    return "\n".join([_HEADER, *_walk(root, [name], None)])


def generate_cli_doc(root: click.Group, docs_dir: Path, *, write: bool = True) -> bool:
    """Write ``docs/CLI.md`` when it differs; return whether it was stale."""
    path = docs_dir / CLI_DOC_NAME
    new = render_cli_docs(root)
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if new == current:
        return False
    if write:
        path.write_text(new, encoding="utf-8", newline="\n")
    return True
