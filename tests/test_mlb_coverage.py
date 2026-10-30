"""MLB Stats API coverage: declarative endpoints, flattening, fan-out, fixtures and extraction."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pytest
import respx
from hypothesis import given, settings
from hypothesis import strategies as st

from baseballpy.core.config import LakeConfig, QuarantineConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.quarantine import Quarantine
from baseballpy.core.schema_tools import snake
from baseballpy.sources import catalog
from baseballpy.sources.mlb_api import generic
from baseballpy.sources.mlb_api.endpoints import (
    BY_NAME,
    ENDPOINTS,
    KEY_OVERRIDES,
    MLB_BASE_URL,
    SUPPORTED,
    Context,
    requests_for,
)
from baseballpy.sources.mlb_api.flatten import (
    flatten_record,
    infer_type,
    iter_records,
    trim_payload,
)
from baseballpy.sources.mlb_api.generic import (
    MlbEndpointExtractor,
    MlbRecordNormalizer,
    UnsupportedEndpointError,
)
from baseballpy.sources.mlb_api.mlb_schema import MLB_SCHEMAS
from baseballpy.sources.mlb_api.schemas import GameType, SportId

FIXTURES = Path(__file__).parent / "fixtures" / "mlb"
PROBE = Path(__file__).parent.parent / "docs" / "mlb_probe.json"
COVERED = [e for e in SUPPORTED if e.name in MLB_SCHEMAS]
SETTINGS = settings(max_examples=60, deadline=None)


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ registry completeness


def test_every_supported_endpoint_has_a_schema_or_a_documented_empty_probe() -> None:
    probe = json.loads(PROBE.read_text(encoding="utf-8"))["endpoints"]
    for ep in SUPPORTED:
        if ep.name in MLB_SCHEMAS:
            assert probe[ep.name]["status"] == "ok", ep.name
        else:
            assert probe[ep.name]["status"] == "empty", f"{ep.name} neither typed nor documented"
    for ep in ENDPOINTS:
        if ep.unsupported is not None:
            assert probe[ep.name]["status"] == "unsupported"
            assert ep.unsupported


def test_registry_matches_schemas_and_fixtures() -> None:
    catalog.register_all()
    assert COVERED, "no endpoint schemas were generated"
    for ep in COVERED:
        spec = get_dataset("mlb_api", ep.name)
        assert spec.schema == MLB_SCHEMAS[ep.name]
        assert spec.partition == ("season" if ep.partitioned else "none")
        assert (FIXTURES / f"{ep.name}.json").exists(), ep.name
        names = set(spec.schema.names)
        assert {snake(k) for k in ep.keys} <= names, f"{ep.name}: key not in schema {ep.keys}"
    assert len({e.name for e in ENDPOINTS}) == len(ENDPOINTS)


def test_endpoint_names_are_snake_case_and_do_not_shadow_hand_written_datasets() -> None:
    hand = {
        "schedule",
        "box_batting",
        "box_pitching",
        "standings",
        "teams",
        "rosters",
        "transactions",
        "draft",
        "venues",
    }
    for ep in ENDPOINTS:
        assert ep.name == snake(ep.name), ep.name
        assert ep.name not in hand


# ------------------------------------------------------------------ flattening


def test_flatten_dots_nested_objects_and_keeps_arrays_as_json() -> None:
    row = flatten_record(
        {"id": 1, "venue": {"id": 2, "location": {"city": "Bronx"}}, "x": [1, 2], "e": []}
    )
    assert row == {"id": 1, "venue.id": 2, "venue.location.city": "Bronx", "x": "[1,2]", "e": None}


def test_iter_records_carries_wrapper_fields_and_fails_loudly_on_shape_changes() -> None:
    payload = {
        "dates": [{"date": "2024-06-23", "totalGames": 2, "games": [{"gamePk": 1}, {"gamePk": 2}]}]
    }
    got = list(iter_records(payload, ("dates", "*", "games")))
    assert [r["gamePk"] for r in got] == [1, 2]
    assert got[0]["dates.date"] == "2024-06-23" and got[0]["dates.totalGames"] == 2
    assert list(iter_records({"other": 1}, ("dates", "*", "games"))) == []
    with pytest.raises(ValueError, match="expected a list"):
        list(iter_records({"dates": {"oops": 1}}, ("dates", "*", "games")))
    with pytest.raises(ValueError, match="expected an object"):
        list(iter_records({"dates": 5}, ("dates", "x")))


def test_trim_payload_keeps_wrapper_and_first_records() -> None:
    payload = {"copyright": "c", "teams": [{"id": i} for i in range(10)]}
    trimmed = trim_payload(payload, ("teams",), 3)
    assert trimmed["copyright"] == "c" and [t["id"] for t in trimmed["teams"]] == [0, 1, 2]
    assert trim_payload([1, 2, 3], (), 2) == [1, 2]


SCALARS = st.one_of(st.none(), st.booleans(), st.integers(-(10**6), 10**6), st.text(max_size=6))
JSON_VALUES = st.recursive(
    SCALARS,
    lambda inner: st.one_of(
        st.lists(inner, max_size=3),
        st.dictionaries(st.text("abc", min_size=1, max_size=3), inner, max_size=3),
    ),
    max_leaves=12,
)


@given(st.dictionaries(st.text("abc", min_size=1, max_size=3), JSON_VALUES, max_size=5))
@SETTINGS
def test_flatten_never_raises_and_only_emits_scalars(obj: dict[str, Any]) -> None:
    row = flatten_record(obj)
    assert all(v is None or isinstance(v, str | int | float | bool) for v in row.values())


def test_infer_type_rules() -> None:
    assert infer_type([None, None]) is None
    assert infer_type([1, 2]) == "int32" and infer_type([1, 5_000_000_000]) == "int64"
    assert infer_type([1, 2.5]) == "float64" and infer_type([True, None]) == "bool"
    assert infer_type(["2024-06-23", None]) == "date32"
    assert infer_type(["2024-06-23T19:05:00Z"]) == "timestamp"
    assert infer_type(["2024-06-23", "x"]) == "string" and infer_type([1, "x"]) == "string"


# ------------------------------------------------------------------ fan-out


def test_requests_for_each_scope() -> None:
    ctx = Context(
        season=2024,
        sport_ids=(1, 11),
        team_ids=(147, 119),
        game_pks=(7, 8),
        leader_categories=("homeRuns", "era"),
        person_ids=(660271, 543037),
        award_ids=("ALMVP", "NLCY"),
        updated_since="2024-06-24T00:00:00Z",
        query="Judge",
    )
    flat = list(requests_for(BY_NAME["ref_game_types"], ctx))
    assert [r.ident for r in flat] == ["ref_game_types"] and flat[0].season is None
    teams = list(requests_for(BY_NAME["teams_season"], ctx))
    assert [r.params["sportId"] for r in teams] == ["1", "11"]
    assert [r.extra for r in teams] == [{"sport_id": 1}, {"sport_id": 11}]
    team_scoped = list(requests_for(BY_NAME["team_roster_active"], ctx))
    assert [r.path for r in team_scoped] == ["v1/teams/147/roster", "v1/teams/119/roster"]
    assert (
        team_scoped[0].extra == {"team_id": 147} and team_scoped[0].params["rosterType"] == "active"
    )
    games = list(requests_for(BY_NAME["game_linescore"], ctx))
    assert [r.path for r in games] == ["v1/game/7/linescore", "v1/game/8/linescore"]
    assert games[1].extra == {"game_pk": 8}
    leaders = next(
        requests_for(
            BY_NAME["stats_leaders"], Context(season=2024, leader_categories=("homeRuns", "era"))
        )
    )
    assert leaders.params["leaderCategories"] == "homeRuns,era"
    affiliates = next(requests_for(BY_NAME["team_affiliates"], ctx))
    assert affiliates.params["teamIds"] == "147,119"
    people = list(requests_for(BY_NAME["award_recipients"], ctx))
    assert [r.path for r in people] == ["v1/awards/ALMVP/recipients", "v1/awards/NLCY/recipients"]
    assert people[0].extra == {"request_award_id": "ALMVP"} and people[0].params["season"] == "2024"
    since = next(requests_for(BY_NAME["people_changes"], ctx))
    assert since.params["updatedSince"] == "2024-06-24T00:00:00Z" and since.season is None
    assert next(requests_for(BY_NAME["people_search"], ctx)).params == {"names": "Judge"}
    person = next(e for e in SUPPORTED if e.scope == "person_season")
    reqs = list(requests_for(person, ctx))
    assert [r.extra for r in reqs] == [{"person_id": 660271}, {"person_id": 543037}]
    assert reqs[0].path == "v1/people/660271/stats"
    idents = [r.ident for e in SUPPORTED for r in requests_for(e, ctx)]
    assert len(idents) == len(set(idents)), "request chunk ids must be unique across endpoints"


def test_season_scope_needs_a_season() -> None:
    with pytest.raises(ValueError, match="season is required"):
        list(requests_for(BY_NAME["teams_season"], Context()))


# ------------------------------------------------------------------ fixtures -> typed tables


@pytest.mark.parametrize("name", [e.name for e in COVERED])
def test_fixture_normalizes_completely(name: str, tmp_path: Path) -> None:
    ep = BY_NAME[name]
    quarantine = Quarantine(QuarantineConfig(base_dir=tmp_path / "q"))
    extra = {"game_pk": 1, "team_id": 2, "sport_id": 1, "person_id": 3, "request_award_id": "X"}
    extra |= {"metric": "launchSpeed", "opposing_team_id": 4, "opposing_player_id": 5}
    upstream = {
        (f.metadata or {}).get(b"upstream", f.name.encode()).decode() for f in MLB_SCHEMAS[name]
    }
    wanted = {k: v for k, v in extra.items() if k in upstream}
    table = MlbRecordNormalizer(quarantine).normalize(ep, _fixture(name), extra=wanted)
    schema = MLB_SCHEMAS[name]
    assert table.schema.names == schema.names
    assert [f.type for f in table.schema] == [f.type for f in schema]
    assert table.num_rows >= 1
    assert table.column("_extras").null_count == table.num_rows, "live fields fully covered"
    assert not list((tmp_path / "q").rglob("*.jsonl")), "no cell was quarantined"
    # a declared override may include dimensions the totals row lacks (a null is one more value)
    nullable = set(ep.keys[1:]) if name in KEY_OVERRIDES else set()
    for key in ep.keys:
        if key in nullable:
            continue
        assert table.column(snake(key)).null_count == 0, f"{name}.{key} has NULL key cells"


def test_unknown_upstream_field_goes_to_extras_and_bad_cells_to_quarantine(tmp_path: Path) -> None:
    ep = BY_NAME["ref_game_types"]
    payload = _fixture("ref_game_types")
    payload[0]["brandNew"] = {"x": 1}
    table = MlbRecordNormalizer().normalize(ep, payload)
    assert json.loads(table.column("_extras")[0].as_py()) == {"brandNew.x": 1}
    assert table.column("_extras")[1].as_py() is None


# ------------------------------------------------------------------ enum vs live data (1.2)


def test_game_type_and_sport_enums_exist_in_the_live_reference_data() -> None:
    game_types = {r["id"] for r in _fixture("ref_game_types")}
    assert {m.value for m in GameType} == game_types, "GameType must equal /v1/gameTypes"
    for member in GameType:
        assert member.value in game_types, f"GameType.{member.name} not served by /v1/gameTypes"
    sports = {r["id"] for r in _fixture("ref_sports")["sports"]}
    for sport in SportId:
        assert sport.value in sports, f"SportId.{sport.name} not served by /v1/sports"


# ------------------------------------------------------------------ extraction


@respx.mock
def test_ingest_flat_endpoint_stores_raw_and_typed_then_serves_from_cache(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(cache_config=lake)
    route = respx.get(f"{MLB_BASE_URL}/v1/gameTypes").mock(
        return_value=httpx.Response(200, json=_fixture("ref_game_types"))
    )
    first = extractor.ingest("ref_game_types", Context())
    assert (first.requests, first.cached) == (1, 0) and first.rows >= 3
    assert extractor.raw.verify("mlb_api", "ref_game_types", "ref_game_types.json")
    again = extractor.ingest("ref_game_types", Context())
    assert (again.cached, route.call_count) == (1, 1)
    stored = generic.read_endpoint("ref_game_types", config=lake)
    assert stored.schema == MLB_SCHEMAS["ref_game_types"] and stored.num_rows == first.rows


@respx.mock
def test_season_scoped_endpoint_writes_a_season_partition(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(cache_config=lake)
    respx.get(f"{MLB_BASE_URL}/v1/teams").mock(
        return_value=httpx.Response(200, json=_fixture("teams_season"))
    )
    report = extractor.ingest("teams_season", Context(season=2024))
    assert report.requests == 1 and report.rows >= 1
    parts = list(lake.processed_dir("mlb_api", "teams_season").rglob("*.parquet"))
    assert [p.parent.name for p in parts] == ["season=2024"]
    assert extractor.ingest("teams_season", Context(season=2024)).cached == 1, (
        "past season is immutable"
    )


@respx.mock
def test_game_scoped_endpoint_adds_game_pk_and_fans_out(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(cache_config=lake)
    for pk in (745000, 775296):
        respx.get(f"{MLB_BASE_URL}/v1/game/{pk}/linescore").mock(
            return_value=httpx.Response(200, json=_fixture("game_linescore"))
        )
    report = extractor.ingest("game_linescore", Context(season=2024, game_pks=(745000, 775296)))
    assert report.requests == 2
    table = generic.read_endpoint("game_linescore", season=2024, config=lake)
    assert sorted(set(table.column("game_pk").to_pylist())) == [745000, 775296]


@respx.mock
def test_paginated_stats_walk_every_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paginated = next((e for e in COVERED if e.paginated), None)
    if paginated is None:
        pytest.skip("no league-wide stats endpoint returned data when schemas were generated")
    monkeypatch.setattr(generic, "PAGE_SIZE", 2)
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(cache_config=lake)
    base = _fixture(paginated.name)
    splits = base["stats"][0]["splits"]
    assert len(splits) >= 3

    def page(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        body = json.loads(json.dumps(base))
        body["stats"][0]["splits"] = splits[offset : offset + 2]
        body["stats"][0]["totalSplits"] = 3
        return httpx.Response(200, json=body)

    route = respx.get(f"{MLB_BASE_URL}/{paginated.path}").mock(side_effect=page)
    report = extractor.ingest(paginated, Context(season=2024))
    assert report.rows == 3 and route.call_count == 2
    assert [int(c.request.url.params["offset"]) for c in route.calls] == [0, 2]
    raw = lake.raw_dir("mlb_api", paginated.name, 2024)
    assert sorted(p.name for p in raw.glob("*.p*.json")) == [
        f"{paginated.name}_2024_sport1.p0.json",
        f"{paginated.name}_2024_sport1.p1.json",
    ]


def test_unsupported_endpoint_is_reported_not_fetched(tmp_path: Path) -> None:
    extractor = MlbEndpointExtractor(cache_config=LakeConfig(home=tmp_path))
    report = extractor.ingest("game_color", Context(season=2024, game_pks=(1,)))
    assert report.unsupported and report.requests == 0
    request = next(requests_for(BY_NAME["game_color"], Context(season=2024, game_pks=(1,))))
    with pytest.raises(UnsupportedEndpointError, match="404"):
        extractor.fetch_request(BY_NAME["game_color"], request)


def test_arrow_types_of_a_known_endpoint() -> None:
    schema = MLB_SCHEMAS["teams_season"]
    assert schema.field("id").type == pa.int32()
    assert schema.field("_extras").type == pa.string()


def test_standings_sentinels_are_values_not_quarantine_noise(tmp_path: Path) -> None:
    from baseballpy.sources.mlb_api.normalizer import MlbApiNormalizer

    record = {
        "team": {"id": 1, "name": "A"},
        "wins": 90,
        "losses": 72,
        "gamesBack": "-",
        "wildCardGamesBack": "+1.5",
        "eliminationNumber": "E",
    }
    other = {
        "team": {"id": 2, "name": "B"},
        "wins": 1,
        "losses": 2,
        "gamesBack": "3.5",
        "wildCardGamesBack": "-",
        "eliminationNumber": "-",
    }
    payload = {"records": [{"division": {"id": 9, "name": "D"}, "teamRecords": [record, other]}]}
    table = MlbApiNormalizer().normalize_standings(payload, season=2024)
    assert table.column("games_back").to_pylist() == [0.0, 3.5]
    assert table.column("wild_card_gb").to_pylist() == [1.5, 0.0]
    assert table.column("elim_num").to_pylist() == [0, None]


def test_all_time_stat_types_are_heavy_and_season_ones_are_not() -> None:
    names = {e.name: e.heavy for e in SUPPORTED}
    assert names["stats_career_hitting"] and names["team_stats_year_by_year_pitching"]
    assert not names["stats_season_hitting"] and not names["teams_season"]


@respx.mock
def test_paginated_request_announcing_a_huge_result_is_refused(tmp_path: Path) -> None:
    from baseballpy.sources.mlb_api.generic import HeavyEndpointError

    ep = next((e for e in COVERED if e.paginated), None)
    if ep is None:
        pytest.skip("no paginated endpoint")
    extractor = MlbEndpointExtractor(cache_config=LakeConfig(home=tmp_path))
    body = _fixture(ep.name)
    body["stats"][0]["totalSplits"] = 192_000
    route = respx.get(f"{MLB_BASE_URL}/{ep.path}").mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(HeavyEndpointError, match="ignores the season"):
        extractor.ingest(ep, Context(season=2024))
    assert route.call_count == 1, "refused after the first page, not after 192 pages"


@respx.mock
def test_endpoint_without_generated_schema_keeps_the_raw_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = BY_NAME["standings_first_half"]
    monkeypatch.delitem(generic.MLB_SCHEMAS, empty.name, raising=False)
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(cache_config=lake)
    route = respx.get(url__regex=rf"{MLB_BASE_URL}/.*").mock(
        return_value=httpx.Response(200, json={"records": []})
    )
    first = extractor.ingest(empty, Context(season=2024))
    assert first.rows == 0 and first.raw_only >= 1 and route.call_count == first.requests
    raw = lake.raw_dir("mlb_api", empty.name, 2024)
    assert [p for p in raw.glob("*.json") if p.name != "manifest.json"]
    again = extractor.ingest(empty, Context(season=2024))
    assert again.cached == again.requests and route.call_count == first.requests


def test_since_and_query_scopes_need_their_value_and_are_unpartitioned() -> None:
    for name in ("people_changes", "game_changes", "people_search"):
        assert not BY_NAME[name].partitioned
        with pytest.raises(ValueError, match="needs ctx"):
            list(requests_for(BY_NAME[name], Context()))


@respx.mock
def test_award_without_a_recipients_list_is_counted_and_not_refetched(tmp_path: Path) -> None:
    from baseballpy.core.http import HttpStatusError

    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(cache_config=lake)
    ok = _fixture("award_recipients")
    respx.get(f"{MLB_BASE_URL}/v1/awards/ALMVP/recipients").mock(
        return_value=httpx.Response(200, json=ok)
    )
    gone = respx.get(f"{MLB_BASE_URL}/v1/awards/AFLHOF/recipients").mock(
        return_value=httpx.Response(404)
    )
    ctx = Context(season=2024, award_ids=("ALMVP", "AFLHOF"))
    first = extractor.ingest("award_recipients", ctx)
    assert (first.requests, first.missing) == (2, 1) and first.rows >= 1
    again = extractor.ingest("award_recipients", ctx)
    assert (again.cached, again.missing, gone.call_count) == (2, 0, 1)
    # endpoints that do not opt in still fail loudly on a 404
    respx.get(f"{MLB_BASE_URL}/v1/sports").mock(return_value=httpx.Response(404))
    with pytest.raises(HttpStatusError):
        extractor.ingest("ref_sports", Context(season=2024))


@respx.mock
def test_sport_without_teams_is_counted_not_fatal(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(cache_config=lake)
    respx.get(f"{MLB_BASE_URL}/v1/teams", params={"sportId": "1"}).mock(
        return_value=httpx.Response(200, json=_fixture("teams_season"))
    )
    respx.get(f"{MLB_BASE_URL}/v1/teams", params={"sportId": "31"}).mock(
        return_value=httpx.Response(404, json={"message": "Object not found"})
    )
    report = extractor.ingest("teams_season", Context(season=2024, sport_ids=(1, 31)))
    assert (report.requests, report.missing) == (2, 1) and report.rows >= 1


@respx.mock
def test_a_5xx_at_a_deep_offset_is_retried_with_smaller_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paginated = next((e for e in COVERED if e.paginated), None)
    if paginated is None:
        pytest.skip("no league-wide stats endpoint returned data when schemas were generated")
    monkeypatch.setattr(generic, "PAGE_SIZE", 4)
    monkeypatch.setattr(generic, "MIN_PAGE_SIZE", 1)
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(cache_config=lake)
    base = _fixture(paginated.name)
    splits = base["stats"][0]["splits"]
    assert len(splits) >= 3

    def page(request: httpx.Request) -> httpx.Response:
        limit, offset = int(request.url.params["limit"]), int(request.url.params["offset"])
        if limit > 2:  # the provider gives up on big pages
            return httpx.Response(503)
        body = json.loads(json.dumps(base))
        body["stats"][0]["splits"] = splits[offset : offset + limit]
        body["stats"][0]["totalSplits"] = 3
        return httpx.Response(200, json=body)

    respx.get(f"{MLB_BASE_URL}/{paginated.path}").mock(side_effect=page)
    report = extractor.ingest(paginated, Context(season=2024))
    assert report.rows == 3


@respx.mock
def test_every_mlb_raw_file_records_an_upstream_fingerprint(tmp_path: Path) -> None:
    from baseballpy.core.upstream import CONTENT_SHA256, stored_fingerprint

    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(cache_config=lake)
    for pk in (745000, 775296):
        respx.get(f"{MLB_BASE_URL}/v1/game/{pk}/linescore").mock(
            return_value=httpx.Response(200, json=_fixture("game_linescore"))
        )
    extractor.ingest("game_linescore", Context(season=2024, game_pks=(745000, 775296)))
    chunks = lake.dataset_manifest("mlb_api", "game_linescore", "raw", 2024).chunks()
    assert chunks
    assert all(
        (fp := stored_fingerprint(entry)) is not None and fp.kind == CONTENT_SHA256
        for entry in chunks.values()
    )


@respx.mock
def test_one_refused_request_does_not_stop_the_others_and_fails_the_job_afterwards(
    tmp_path: Path,
) -> None:
    from baseballpy.core.http import HttpStatusError
    from baseballpy.ingest.types import JobStatus, make_job
    from baseballpy.sources.mlb_api.adapter import _result

    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(cache_config=lake)
    respx.get(f"{MLB_BASE_URL}/v1/game/745000/linescore").mock(return_value=httpx.Response(406))
    respx.get(f"{MLB_BASE_URL}/v1/game/775296/linescore").mock(
        return_value=httpx.Response(200, json=_fixture("game_linescore"))
    )
    with pytest.raises(HttpStatusError):
        extractor.ingest("game_linescore", Context(season=2024, game_pks=(745000, 775296)))
    report = extractor.ingest(
        "game_linescore", Context(season=2024, game_pks=(745000, 775296)), keep_going=True
    )
    assert report.requests == 2 and report.rows > 0
    assert len(report.errors) == 1 and "406" in report.errors[0]
    result = _result(make_job("mlb_api", "season", season=2024), [report])
    assert result.status == JobStatus.FAILED and result.rows == report.rows
    assert "1 request(s) refused" in result.detail and "game_linescore" in (result.error or "")
