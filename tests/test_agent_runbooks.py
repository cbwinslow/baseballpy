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
