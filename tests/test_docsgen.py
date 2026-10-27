"""Generated column dictionaries: committed docs must match the registry exactly."""

import json
from pathlib import Path

from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.core.datasets import DATASETS, get_dataset
from baseballpy.docsgen import generate_docs, render_dataset, render_source_doc, stale_blocks
from baseballpy.sources import catalog

DOCS = Path(__file__).parent.parent / "docs"


def test_committed_docs_are_not_stale() -> None:
    changed = generate_docs(DOCS, write=False)
    stale = [name for name, was in changed.items() if was]
    assert stale == [], "run `baseballpy docs generate` and commit the result"


def test_every_dataset_has_a_generated_block_with_every_column() -> None:
    catalog.register_all()
    for source in {spec.source for spec in DATASETS.values()}:
        text = (DOCS / "sources" / f"{source}.md").read_text(encoding="utf-8")
        specs = [s for s in DATASETS.values() if s.source == source]
        assert stale_blocks(text, specs) == []
        for spec in specs:
            for field in spec.schema:
                assert f"| `{field.name}` |" in text, (spec.key, field.name)


def test_render_dataset_documents_view_key_types_and_upstream_names() -> None:
    catalog.register_all()
    block = render_dataset(get_dataset("retrosheet", "schedule"), {"game_date": "Scheduled date"})
    assert "<!-- BEGIN GENERATED:retrosheet.schedule -->" in block
    assert "### Dataset: schedule" in block
    assert "`retrosheet_schedule`" in block and "season=YYYY" in block
    assert "| `game_date` | date32[day] (`%Y%m%d`) | yes | `Date` | Scheduled date |" in block
    assert "| `visitor_team` | string | yes | `Visitor` |  |" in block
    assert "`_extras`" in block


def test_blocks_are_replaced_in_place_and_new_ones_appended(tmp_path: Path) -> None:
    catalog.register_all()
    spec = get_dataset("lahman", "People")
    first = render_source_doc("# Lahman\n\nintro\n", [spec], tmp_path)
    assert first.count("BEGIN GENERATED:lahman.People") == 1 and "intro" in first
    (tmp_path / "columns").mkdir()
    (tmp_path / "columns" / "lahman.json").write_text(
        json.dumps({"People": {"playerID": "Lahman player id"}}), encoding="utf-8"
    )
    second = render_source_doc(first, [spec], tmp_path)
    assert second.count("BEGIN GENERATED:lahman.People") == 1
    assert "Lahman player id" in second and "intro" in second
    assert render_source_doc(second, [spec], tmp_path) == second  # idempotent


def test_cli_check_fails_on_stale_docs_and_generate_fixes_them(tmp_path: Path) -> None:
    (tmp_path / "sources").mkdir()
    runner = CliRunner()
    stale = runner.invoke(main, ["docs", "generate", "--docs-dir", str(tmp_path), "--check"])
    assert stale.exit_code == 1 and "stale" in stale.output
    done = runner.invoke(main, ["docs", "generate", "--docs-dir", str(tmp_path)])
    assert done.exit_code == 0 and (tmp_path / "sources" / "retrosheet.md").exists()
    clean = runner.invoke(main, ["docs", "generate", "--docs-dir", str(tmp_path), "--check"])
    assert clean.exit_code == 0 and "up to date" in clean.output
