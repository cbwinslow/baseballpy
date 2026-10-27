"""Parameterized stat types: fan-out dimensions, opt-in families and the audit accounting."""

from pathlib import Path

import pytest

from baseballpy.audit import audit_mlb
from baseballpy.core.config import LakeConfig
from baseballpy.sources.mlb_api import api as api_mod
from baseballpy.sources.mlb_api.endpoints import Context, MlbEndpoint, requests_for


def _person(name: str, params: dict[str, str], fan_out: tuple[str, ...]) -> MlbEndpoint:
    return MlbEndpoint(
        name,
        "v1/people/{person_id}/stats",
        ("stats", "*", "splits"),
        "synthetic",
        ("person_id",),
        "person_season",
        {"stats": "x", "group": "pitching", "season": "{season}", **params},
        "stats",
        fan_out=fan_out,
    )


def test_metric_fan_out_is_person_times_metric_with_injected_columns() -> None:
    ep = _person("people_stats_x_pitching", {"metrics": "{metric}"}, ("metric",))
    ctx = Context(season=2024, person_ids=(1, 2), metrics=("releaseSpeed", "launchSpeed"))
    reqs = list(requests_for(ep, ctx))
    assert len(reqs) == 4 and len({r.ident for r in reqs}) == 4
    assert {r.extra["metric"] for r in reqs} == {"releaseSpeed", "launchSpeed"}
    assert reqs[0].params["metrics"] == "releaseSpeed" and reqs[0].extra["person_id"] == 1
    assert reqs[0].path == "v1/people/1/stats"


def test_metric_the_provider_answers_with_500_is_never_requested() -> None:
    ep = _person("people_stats_metric_averages_pitching", {"metrics": "{metric}"}, ("metric",))
    ctx = Context(season=2024, person_ids=(1,), metrics=("barreledBall", "launchSpeed"))
    assert [r.extra["metric"] for r in requests_for(ep, ctx)] == ["launchSpeed"]
    other = _person("people_stats_metric_log_pitching", {"metrics": "{metric}"}, ("metric",))
    assert len(list(requests_for(other, ctx))) == 2


def test_opposing_fan_out_needs_its_ids_and_yields_nothing_without_them() -> None:
    ep = _person(
        "people_stats_vs_x_pitching",
        {"opposingTeamId": "{opposing_team_id}"},
        ("opposing_team_id",),
    )
    assert list(requests_for(ep, Context(season=2024, person_ids=(1,)))) == []
    reqs = list(
        requests_for(ep, Context(season=2024, person_ids=(1,), opposing_team_ids=(147, 119)))
    )
    assert [r.params["opposingTeamId"] for r in reqs] == ["147", "119"]
    assert reqs[1].extra == {"person_id": 1, "opposing_team_id": 119}


def test_sit_codes_are_sent_in_one_request() -> None:
    ep = _person("people_stats_splits_pitching", {"sitCodes": "{sit_codes}"}, ())
    reqs = list(requests_for(ep, Context(season=2024, person_ids=(7,), sit_codes=("h", "a", "d"))))
    assert len(reqs) == 1 and reqs[0].params["sitCodes"] == "h,a,d"


def test_endpoint_without_season_param_omits_it() -> None:
    ep = MlbEndpoint(
        "people_stats_projected_zips_pitching",
        "v1/people/{person_id}/stats",
        ("stats", "*", "splits"),
        "synthetic",
        ("person_id",),
        "person_season",
        {"stats": "projected_Zips", "group": "pitching"},
        "stats",
    )
    (req,) = requests_for(ep, Context(season=2024, person_ids=(5,)))
    assert "season" not in req.params


def test_league_wide_situational_splits_are_heavy() -> None:
    heavy = MlbEndpoint(
        "stats_stat_splits_hitting", "v1/stats", (), "d", ("season",), "season", {}, paginated=True
    )
    plain = MlbEndpoint(
        "people_stats_stat_splits_hitting", "v1/stats", (), "d", ("season",), "season", {}
    )
    assert heavy.heavy and not plain.heavy


def test_people_stats_families_are_validated_and_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metric = _person("people_stats_metric_log_pitching", {"metrics": "{metric}"}, ("metric",))
    versus = _person(
        "people_stats_vs_team_pitching",
        {"opposingTeamId": "{opposing_team_id}"},
        ("opposing_team_id",),
    )
    seen: list[str] = []

    class FakeEndpoints:
        def ingest(
            self, endpoint: MlbEndpoint, ctx: Context, refresh: bool = False, **kw: object
        ) -> str:
            seen.append(endpoint.name)
            return endpoint.name

    source = api_mod.MlbApiSource(LakeConfig(home=tmp_path))
    monkeypatch.setattr(source, "endpoints", FakeEndpoints())
    monkeypatch.setattr(api_mod, "SUPPORTED", (metric, versus))
    assert source.ingest_people_stats(2024, person_ids=(1,)) == []
    assert source.ingest_people_stats(2024, person_ids=(1,), families=("metrics",)) == [metric.name]
    with pytest.raises(ValueError, match="needs opposing_team_ids"):
        source.ingest_people_stats(2024, person_ids=(1,), families=("matchups",))
    done = source.ingest_people_stats(
        2024, person_ids=(1,), families=("matchups",), opposing_team_ids=(147,)
    )
    assert done == [versus.name]
    with pytest.raises(ValueError, match="unknown people-stats families"):
        source.ingest_people_stats(2024, person_ids=(1,), families=("everything",))


def test_audit_accounts_for_unsupported_stat_types(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    import respx

    from baseballpy.core.config import RateLimitConfig
    from baseballpy.core.http import HttpClient
    from baseballpy.sources.mlb_api.endpoints import ROSTER_TYPES, STANDINGS_TYPES
    from baseballpy.sources.mlb_api.schemas import GameType

    monkeypatch.setattr(
        "baseballpy.audit.UNSUPPORTED_STAT_TYPES", (("advanced", "2026-10-27", ("bare",)),)
    )
    api = "https://statsapi.mlb.com/api/v1"
    with respx.mock:
        for name, rows in {
            "standingsTypes": [{"name": n} for n in STANDINGS_TYPES],
            "rosterTypes": [{"parameter": n} for n in ROSTER_TYPES],
            "gameTypes": [{"id": m.value} for m in GameType],
            "statTypes": [{"displayName": "advanced"}, {"displayName": "neverHeardOf"}],
            "statGroups": [{"displayName": "hitting"}],
        }.items():
            respx.get(f"{api}/{name}").mock(return_value=httpx.Response(200, json=rows))
        client = HttpClient(
            RateLimitConfig(
                host_rates={"statsapi.mlb.com": 1000.0}, default_requests_per_second=1000.0
            ),
            http2=False,
        )
        try:
            findings = audit_mlb(client)
        finally:
            client.close()
    assert [f.item for f in findings] == ["stat type: neverHeardOf"]


def test_sport_and_team_fan_out_endpoints_tolerate_the_providers_404() -> None:
    from baseballpy.sources.mlb_api.endpoints import ENDPOINTS, FAN_OUT_MARKERS

    fanned = [
        e
        for e in ENDPOINTS
        if not e.paginated
        and any(m in t for m in FAN_OUT_MARKERS for t in (e.path, *map(str, e.params.values())))
    ]
    assert {e.name for e in fanned} >= {"teams_season", "team_alumni"}
    assert all(e.tolerate_missing for e in fanned)
