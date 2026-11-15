"""`baseballpy live`: the dry run reads the schedule once and changes nothing; a run wires the journal on."""

from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from click.testing import CliRunner

from baseballpy import cli_live
from baseballpy.cli import main
from baseballpy.sources.mlb_api.live.schedule import SCHEDULE_URL
from baseballpy.sources.mlb_api.live.supervisor import LiveReport


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path))


@respx.mock
def test_the_dry_run_lists_the_games_and_writes_nothing(tmp_path: Path) -> None:
    payload = {
        "dates": [
            {
                "games": [
                    {"gamePk": 745000, "season": "2026", "status": {"abstractGameState": "Live"}},
                    {"gamePk": 745001, "season": "2026", "status": {"abstractGameState": "Final"}},
                ]
            }
        ]
    }
    route = respx.get(SCHEDULE_URL).mock(return_value=httpx.Response(200, json=payload))
    result = CliRunner().invoke(main, ["live", "--dry-run", "--sports", "1,11"])
    assert result.exit_code == 0, result.output
    text = " ".join(result.output.split())
    assert "745000" in text and "745001" in text
    assert route.call_count == 2, "yesterday and today, one request each"
    assert route.calls[0].request.url.params["sportId"] == "1,11"
    assert not (tmp_path / "raw").exists() and not (tmp_path / "processed").exists(), (
        "no data written"
    )


def test_a_bad_sport_list_is_refused() -> None:
    result = CliRunner().invoke(main, ["live", "--dry-run", "--sports", "x"])
    assert result.exit_code != 0 and "comma-separated sport ids" in result.output


def test_a_run_turns_the_journal_on_and_raises_the_idle_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeSupervisor:
        def __init__(self, **kwargs: Any) -> None:
            seen.update(kwargs)
            self.report = LiveReport()

        async def run(self, stop: Any) -> LiveReport:
            return self.report

    monkeypatch.setattr(cli_live, "LiveSupervisor", FakeSupervisor)
    result = CliRunner().invoke(main, ["live", "--max-games", "3", "--commit-seconds", "5"])
    assert result.exit_code == 0, result.output
    config = seen["config"]
    assert config.journal is True and config.max_live_games == 3 and config.commit_seconds == 5.0
    assert config.max_inactivity_minutes >= cli_live.MIN_IDLE_MINUTES
    assert seen["stream"].__self__.journal_enabled is True
    assert seen["sink"].spec.key == "mlb_api.game_live_events"
