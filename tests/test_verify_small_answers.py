"""Small low-volume MLB answers are fetched twice and the largest body wins (ADR 60)."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.http import HttpClient
from baseballpy.sources.mlb_api.endpoints import BY_NAME, Context
from baseballpy.sources.mlb_api.generic import MlbEndpointExtractor

FIXTURES = Path(__file__).parent / "fixtures" / "mlb"
URL = "https://statsapi.mlb.com/api/v1/gameTypes"


def _rows(count: int) -> list[dict[str, str]]:
    full = json.loads((FIXTURES / "ref_game_types.json").read_text(encoding="utf-8"))
    return full[:count]


def _extractor(tmp_path: Path, **rate: object) -> MlbEndpointExtractor:
    config = RateLimitConfig(statsapi_rps=1000.0, **rate)  # type: ignore[arg-type]
    return MlbEndpointExtractor(
        cache_config=LakeConfig(home=tmp_path), http=HttpClient(config, http2=False)
    )


def _run(extractor: MlbEndpointExtractor) -> int:
    try:
        return extractor.ingest(BY_NAME["ref_game_types"], Context()).rows
    finally:
        extractor.http.close()


@respx.mock
def test_a_partial_first_answer_is_replaced_by_the_full_one(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    route = respx.get(URL).mock(
        side_effect=[
            httpx.Response(200, json=_rows(3)),
            httpx.Response(200, json=_rows(11)),
            httpx.Response(200, json=_rows(11)),
        ]
    )
    with caplog.at_level("WARNING"):
        rows = _run(_extractor(tmp_path))
    assert rows == 11 and route.call_count == 3
    message = " ".join(
        r.getMessage() for r in caplog.records if "provider_inconsistent" in r.getMessage()
    )
    assert "ref_game_types" in message and "kept the largest" in message


@respx.mock
def test_identical_answers_cost_exactly_one_extra_request(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=_rows(11)))
    with caplog.at_level("WARNING"):
        rows = _run(_extractor(tmp_path))
    assert rows == 11 and route.call_count == 2
    assert "provider_inconsistent" not in caplog.text


@respx.mock
def test_big_many_disabled_and_non_200_answers_are_not_verified(tmp_path: Path) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=_rows(11)))
    # an answer above verify_max_bytes
    assert _run(_extractor(tmp_path / "big", verify_max_bytes=10)) == 11
    assert route.call_count == 1
    # verification switched off
    route.reset()
    assert _run(_extractor(tmp_path / "off", verify_max_requests=0)) == 11
    assert route.call_count == 1
    # a call with more requests than verify_max_requests (three teams, limit two): one each;
    # with the limit raised to three every request is fetched twice
    roster = respx.get(url__regex=r"https://statsapi\.mlb\.com/api/v1/teams/\d+/roster.*").mock(
        return_value=httpx.Response(200, json={"roster": []})
    )
    ctx = Context(season=2024, team_ids=[1, 2, 3])
    for limit, expected in ((2, 3), (3, 6)):
        roster.reset()
        extractor = _extractor(tmp_path / f"roster{limit}", verify_max_requests=limit)
        try:
            extractor.ingest(BY_NAME["team_roster_active"], ctx)
        finally:
            extractor.http.close()
        assert roster.call_count == expected, (limit, roster.call_count)
    # a non-200 answer (a tolerated 404) is returned as it is, without a second request
    missing = respx.get("https://statsapi.mlb.com/api/v1/nothing").mock(
        return_value=httpx.Response(404)
    )
    verified = _extractor(tmp_path / "404")
    try:
        result = verified._verified_get(
            BY_NAME["ref_game_types"], "https://statsapi.mlb.com/api/v1/nothing", {}, (200, 404)
        )
    finally:
        verified.http.close()
    assert result.status == 404 and missing.call_count == 1


@respx.mock
def test_three_different_answers_keep_the_largest_and_warn(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    route = respx.get(URL).mock(
        side_effect=[
            httpx.Response(200, json=_rows(5)),
            httpx.Response(200, json=_rows(9)),
            httpx.Response(200, json=_rows(7)),
        ]
    )
    with caplog.at_level("WARNING"):
        rows = _run(_extractor(tmp_path))
    assert rows == 9 and route.call_count == 3
    assert "3 different bodies" in caplog.text
