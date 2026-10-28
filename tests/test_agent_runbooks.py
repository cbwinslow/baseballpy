"""The versioned goal-seek prompt keeps the rules the `agent-runbooks` spec requires."""

from pathlib import Path

PROMPT = Path(__file__).resolve().parent.parent / "docs" / "agents" / "GOAL_SEEK_PROMPT.md"


def test_goal_seek_prompt_states_every_required_rule() -> None:
    text = PROMPT.read_text(encoding="utf-8")
    lowered = text.lower()
    for needle in (
        "AGENTS.md",  # contract files are read first
        "openspec is required",  # a change is opened before editing
        "never leave upstream data behind",
        "unsupported",  # verdicts need evidence
        "never push",  # commits are local
        "search before you work around",  # cited web research
    ):
        assert needle.lower() in lowered, needle


def test_goal_seek_prompt_is_a_loop_with_verification() -> None:
    text = PROMPT.read_text(encoding="utf-8")
    assert "PLAN" in text
    assert "pytest" in text
    assert "ruff" in text
    assert "mypy" in text


def _load_project_map():  # type: ignore[no-untyped-def]
    import importlib.util

    path = PROMPT.parent.parent.parent / "scripts" / "project_map.py"
    spec = importlib.util.spec_from_file_location("project_map", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_open_task_is_in_the_backlog() -> None:
    backlog = (PROMPT.parent / "BACKLOG.md").read_text(encoding="utf-8")
    missing = [
        f"{change} {num}"
        for change, num in _load_project_map().open_tasks()
        if f"`{change} {num}`" not in backlog
    ]
    assert not missing, f"open tasks missing from docs/agents/BACKLOG.md: {missing}"


def test_backlog_names_no_task_that_is_done_or_unknown() -> None:
    import re

    backlog = (PROMPT.parent / "BACKLOG.md").read_text(encoding="utf-8")
    project_map = _load_project_map()
    open_now = {f"{c} {n}" for c, n in project_map.open_tasks()}
    known = {c.name for c in project_map.active_changes()}
    for ref in re.findall(r"`([a-z][a-z0-9-]+ \d+(?:\.\d+)?)`", backlog):
        assert ref.split(" ")[0] in known, f"unknown change in backlog: {ref}"
        assert ref in open_now, f"backlog lists a finished task: {ref}"


def test_project_map_is_current() -> None:
    project_map = _load_project_map()
    assert project_map.OUTPUT.read_text(encoding="utf-8") == project_map.render()
