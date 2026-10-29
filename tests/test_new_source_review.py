"""The source-review generator renders complete, traceable cards for every source."""

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIELDS = (
    "Change task",
    "Stage",
    "Executor",
    "Files",
    "Tools (reuse check)",
    "Inputs",
    "Steps",
    "Done when",
    "Record",
)


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "new_source_review", ROOT / "scripts" / "new_source_review.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = _script()


@pytest.mark.parametrize("source", sorted(gen.SOURCES))
def test_every_source_gets_complete_cards_that_match_its_tasks(source: str) -> None:
    cards = gen.render_cards(source)
    tasks = gen.render_tasks(source)
    for text in (cards, tasks, gen.render_proposal(source), gen.render_design(source)):
        assert "$" not in text, "an unfilled placeholder is left"
    blocks = re.split(r"^### (?=[A-Z]-\d+ )", cards, flags=re.M)[1:]
    assert len(blocks) == len(gen.CARDS)
    for block in blocks:
        for field in FIELDS:
            assert f"**{field}:**" in block, (source, block[:30], field)
    task_numbers = re.findall(r"- \[ \] (\d+\.\d+) ", tasks)
    card_refs = re.findall(rf"`{source}-source-review (\d+\.\d+)`", cards)
    assert task_numbers == card_refs == [c.num for c in gen.CARDS]
    prefix = gen.SOURCES[source][1]
    assert re.findall(r"\(([A-Z]-\d+)\)$", tasks, flags=re.M) == [
        f"{prefix}-{i:02d}" for i in range(1, len(gen.CARDS) + 1)
    ]


def test_standing_standards_are_in_every_review() -> None:
    text = " ".join(
        " ".join((c.title, c.files, c.tools, c.inputs, *c.steps, c.done)) for c in gen.CARDS
    )
    for needle in (
        "is_current",  # shared currency check (ADR 43)
        "cache check --upstream",
        "baseballpy export",  # export checklist (ADR 46)
        "Onboarding a source",
        "build_column_descriptions",  # cited descriptions (ADR 34)
        "never invented",
        "schema-sync test",  # every column on the record types
        "registry",  # no hard-coded dataset names
    ):
        assert needle in text, needle


def test_backlog_rows_continue_the_numbering_and_chain_the_tasks() -> None:
    existing = "| B-9 | x | DONE | y |\n| B-41 | x | DONE | y |\n"
    assert gen.next_backlog_number(existing) == 42
    rows = gen.render_backlog("lahman", existing)
    ids = re.findall(r"\| (B-\d+) \|", rows)
    assert ids[0] == "B-42" and len(ids) == len(gen.CARDS)
    assert "| READY |" in rows.splitlines()[5] and "after B-42" in rows
    assert all(f"`lahman-source-review {c.num}`" in rows for c in gen.CARDS)


def test_generator_writes_the_files_once_and_refuses_to_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text("| B-1 | a | DONE | b |\n", encoding="utf-8")
    monkeypatch.setattr(gen, "CHANGES", tmp_path / "changes")
    monkeypatch.setattr(gen, "TRACKS", tmp_path / "tracks")
    monkeypatch.setattr(gen, "BACKLOG", backlog)
    assert gen.main(["retrosheet"]) == 0
    assert (tmp_path / "changes" / "retrosheet-source-review" / "tasks.md").exists()
    assert (tmp_path / "tracks" / "03-retrosheet.md").exists()
    assert "retrosheet-source-review 4.1" in backlog.read_text(encoding="utf-8")
    assert gen.main(["retrosheet"]) == 1  # second run refuses
    assert gen.main(["statcast", "--dry-run"]) == 0
    assert not (tmp_path / "tracks" / "04-statcast.md").exists()


def test_scorecard_has_one_row_per_source_in_review_order() -> None:
    spec = importlib.util.spec_from_file_location(
        "project_map", ROOT / "scripts" / "project_map.py"
    )
    assert spec and spec.loader
    project_map = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(project_map)
    rows = project_map.source_rows()
    assert [row.split("|")[1].strip(" `") for row in rows] == list(gen.SOURCES)
    chadwick = [c.strip() for c in rows[0].split("|")[1:-1]]
    assert chadwick[2] == "archived" and chadwick[3:6] == ["yes", "yes", "yes"]
    assert all(len(row.split("|")) == 10 for row in rows)  # eight columns, no broken cell
