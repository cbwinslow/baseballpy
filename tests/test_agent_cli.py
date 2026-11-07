"""Tests for AI agent coordination CLI commands (claim, release, board)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from baseballpy.cli import main

SAMPLE_BOARD_TEMPLATE = """# AI Agent Bulletin Board & Coordination Center

## Active Checkouts (Locked — Do Not Disturb)

## Recent Completed Handoffs

## Team Notes & Notices
"""


@pytest.fixture
def agent_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Set up temporary docs/agents directory for testing."""
    agents_dir = tmp_path / "docs" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    board_file = agents_dir / "AGENT_BOARD.md"
    log_file = agents_dir / "agent_log.jsonl"
    board_file.write_text(SAMPLE_BOARD_TEMPLATE, encoding="utf-8")

    # Mock find_project_root so baseballpy agent uses tmp_path
    monkeypatch.setattr("baseballpy.cli_agent.find_project_root", lambda: tmp_path)
    return board_file, log_file


def test_agent_board_command(agent_workspace: tuple[Path, Path]) -> None:
    board_file, _ = agent_workspace
    runner = CliRunner()

    # Empty checkouts
    result = runner.invoke(main, ["agent", "board"])
    assert result.exit_code == 0
    assert "No active checkouts" in result.output

    # Add an active checkout manually
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    block = (
        "## Active Checkouts (Locked — Do Not Disturb)\n\n"
        "- **Task:** B-101\n"
        "  - **Agent:** TestAgent\n"
        f"  - **Claimed At:** {now_str}\n"
        "  - **Locked Areas:**\n"
        "    - `src/baseballpy/test.py`\n"
        "  - **Status:** In progress\n\n"
    )
    board_file.write_text(
        SAMPLE_BOARD_TEMPLATE.replace("## Active Checkouts (Locked — Do Not Disturb)\n\n", block),
        encoding="utf-8",
    )

    result2 = runner.invoke(main, ["agent", "board"])
    assert result2.exit_code == 0
    assert "B-101" in result2.output
    assert "TestAgent" in result2.output


def test_agent_claim_and_release_flow(agent_workspace: tuple[Path, Path]) -> None:
    board_file, log_file = agent_workspace
    runner = CliRunner()

    # 1. Claim task
    res_claim = runner.invoke(
        main,
        [
            "agent",
            "claim",
            "B-999",
            "--agent",
            "Gemini",
            "--files",
            "src/foo.py,tests/bar.py",
            "--note",
            "Testing",
        ],
    )
    assert res_claim.exit_code == 0
    assert "Claimed task: B-999 by Gemini" in res_claim.output

    board_text = board_file.read_text(encoding="utf-8")
    assert "B-999" in board_text
    assert "Gemini" in board_text
    assert "src/foo.py" in board_text

    log_text = log_file.read_text(encoding="utf-8")
    assert "TASK_CLAIMED" in log_text
    assert "B-999" in log_text

    # 2. Release task
    res_release = runner.invoke(
        main,
        ["agent", "release", "B-999", "Successfully implemented foo", "--agent", "Gemini"],
    )
    assert res_release.exit_code == 0
    assert "Released task: B-999" in res_release.output

    board_text_after = board_file.read_text(encoding="utf-8")
    # Should not be in Active Checkouts anymore
    active_section = board_text_after.split("## Recent Completed Handoffs")[0]
    assert "B-999" not in active_section

    # Should be in Recent Completed Handoffs
    handoffs_section = board_text_after.split("## Recent Completed Handoffs")[1]
    assert "B-999" in handoffs_section
    assert "Successfully implemented foo" in handoffs_section

    # Check log
    log_text_after = log_file.read_text(encoding="utf-8")
    assert "TASK_COMPLETED" in log_text_after


def test_agent_claim_collision_refusal(agent_workspace: tuple[Path, Path]) -> None:
    runner = CliRunner()

    res1 = runner.invoke(main, ["agent", "claim", "B-123", "--agent", "Agent1"])
    assert res1.exit_code == 0

    # Second claim within 4h fails
    res2 = runner.invoke(main, ["agent", "claim", "B-123", "--agent", "Agent2"])
    assert res2.exit_code == 1
    assert "Refused:" in res2.output
    assert "already claimed by Agent1" in res2.output


def test_agent_claim_stale_lock_override(agent_workspace: tuple[Path, Path]) -> None:
    board_file, log_file = agent_workspace
    runner = CliRunner()

    # Create stale checkout (5 hours ago)
    stale_time = (datetime.now(UTC) - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M UTC")
    block = (
        "## Active Checkouts (Locked — Do Not Disturb)\n\n"
        "- **Task:** B-555\n"
        "  - **Agent:** OldAgent\n"
        f"  - **Claimed At:** {stale_time}\n"
        "  - **Locked Areas:**\n"
        "    - `(none specified)`\n"
        "  - **Status:** Abandoned\n\n"
    )
    board_file.write_text(
        SAMPLE_BOARD_TEMPLATE.replace("## Active Checkouts (Locked — Do Not Disturb)\n\n", block),
        encoding="utf-8",
    )

    # Claiming B-555 should succeed with warning
    res = runner.invoke(main, ["agent", "claim", "B-555", "--agent", "NewAgent"])
    assert res.exit_code == 0
    assert "Warning: Overriding stale lock" in res.output
    assert "Claimed task: B-555 by NewAgent" in res.output

    log_text = log_file.read_text(encoding="utf-8")
    assert "STALE_LOCK_OVERRIDDEN" in log_text


def test_agent_claim_force_override(agent_workspace: tuple[Path, Path]) -> None:
    runner = CliRunner()

    res1 = runner.invoke(main, ["agent", "claim", "B-777", "--agent", "Agent1"])
    assert res1.exit_code == 0

    # Force override of active lock
    res2 = runner.invoke(main, ["agent", "claim", "B-777", "--agent", "Agent2", "--force"])
    assert res2.exit_code == 0
    assert "Claimed task: B-777 by Agent2" in res2.output
