"""The endpoint cross-check lists every registry route and is kept current."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import endpoint_crosscheck as cross  # noqa: E402

from baseballpy.sources.mlb_api.endpoints import ENDPOINTS  # noqa: E402


def test_a_route_matches_only_where_its_name_ends() -> None:
    assert cross.mentions("GET /api/v1/teams?x=1", "v1/teams")
    assert not cross.mentions("GET /api/v1/teams/stats", "v1/teams")
    assert cross.mentions("/api/v1/people/{personId}/stats", "v1/people/{}/stats")


def test_the_report_lists_every_distinct_route_and_is_current() -> None:
    report = cross.build()
    for endpoint in ENDPOINTS:
        assert f"`{cross.route_key(endpoint.path)}`" in report
    assert cross.OUT.read_text(encoding="utf-8") == report  # run scripts/endpoint_crosscheck.py
