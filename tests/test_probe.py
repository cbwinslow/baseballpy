"""``baseballpy probe`` reports each provider route's answer and fails when one is down."""

import httpx
import respx
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.probe import canaries


def _mock_all(status_for: dict[str, int]) -> None:
    for canary in canaries(2025):
        status = next((s for part, s in status_for.items() if part in canary.url), 200)
        respx.get(canary.url).mock(return_value=httpx.Response(status, content=b"x"))


@respx.mock
def test_probe_passes_when_every_route_answers() -> None:
    _mock_all({})
    result = CliRunner().invoke(main, ["probe", "--season", "2025"])
    assert result.exit_code == 0, result.output
    assert "FAILED" not in result.output


@respx.mock
def test_probe_names_the_failing_route_and_its_fallback() -> None:
    _mock_all({"/api/v1/stats?": 406})
    respx.get("https://statsapi.mlb.com/api/v1/stats").mock(return_value=httpx.Response(406))
    result = CliRunner().invoke(main, ["probe", "--season", "2025"])
    assert result.exit_code == 1
    assert "406" in result.output and "FAILED" in result.output
    assert "hydrate" in result.output  # the fallback is named
