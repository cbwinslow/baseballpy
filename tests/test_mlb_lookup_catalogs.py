"""The MLB lookup lists added by ADR 132: registered, typed, keyed and flattened without special cases."""

import json
from pathlib import Path
from typing import Any

from baseballpy.core.schema_tools import snake
from baseballpy.sources.mlb_api.endpoints import BY_NAME, SUPPORTED
from baseballpy.sources.mlb_api.flatten import iter_records
from baseballpy.sources.mlb_api.generic import MlbRecordNormalizer
from baseballpy.sources.mlb_api.mlb_schema import MLB_SCHEMAS

FIXTURES = Path(__file__).parent / "fixtures" / "mlb"

#: routes of ``/v1`` that answered HTTP 200 without parameters on 2026-11-14 (ADR 132)
LOOKUP_ROUTES = [
    "achievementStatuses",
    "coachingVideoTypes",
    "eventStatus",
    "fielderDetailTypes",
    "freeGameTypes",
    "gamedayTypes",
    "groupByTypes",
    "highLow/types",
    "mediaState",
    "milestoneDurations",
    "milestoneStatistics",
    "milestoneTypes",
    "milestoneLookups",
    "moundVisitTypes",
    "performerTypes",
    "pitchCodes",
    "playerStatusCodes",
    "roofTypes",
    "ruleSettings",
    "runnerDetailTypes",
    "sortModifiers",
    "statFields",
    "statcastPositionTypes",
    "streaks/types",
    "trackingSoftwareVersions",
    "trackingSystemOwners",
    "trackingVendors",
    "trackingVersions",
    "transactionTypes",
    "violationTypes",
    "videoResolutionTypes",
    "weatherTrajectoryConfidences",
    "sky",
    "stats/search/params",
    "stats/search/groupByTypes",
    "stats/search/stats",
    "stats/search/config",
    "lookup/values/all",
]
DICT_OF_LISTS = ("milestoneLookups", "streaks/types", "stats/search/config", "lookup/values/all")


def _name(route: str) -> str:
    return f"ref_{snake(route)}"


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_every_lookup_route_is_a_registered_typed_dataset_with_its_own_path() -> None:
    names = [_name(r) for r in LOOKUP_ROUTES]
    assert len(set(names)) == len(names)
    supported = {e.name for e in SUPPORTED}
    for route in LOOKUP_ROUTES:
        ep = BY_NAME[_name(route)]
        assert ep.path == f"v1/{route}" and ep.scope == "flat"
        assert ep.name in supported and ep.name in MLB_SCHEMAS, route
        assert (FIXTURES / f"{ep.name}.json").exists(), route


def test_game_pace_is_kept_as_unsupported_with_its_probe_evidence() -> None:
    ep = BY_NAME["ref_game_pace"]
    assert ep.unsupported and ep.verified_on == "2026-11-14" and ep.tried
    assert ep.name not in MLB_SCHEMAS


def test_a_list_of_objects_a_list_of_strings_and_a_dict_of_lists_flatten_with_the_same_code() -> (
    None
):
    sky = list(iter_records(_fixture("ref_sky"), BY_NAME["ref_sky"].records))
    assert sky and set(sky[0]) == {"code", "description"}
    strings = list(
        iter_records(
            _fixture("ref_coaching_video_types"), BY_NAME["ref_coaching_video_types"].records
        )
    )
    assert strings and all(set(r) == {"value"} for r in strings)
    lists = list(iter_records(_fixture("ref_milestone_lookups"), ("@",)))
    assert {r["key"] for r in lists} == {
        "achievementStatuses",
        "milestoneTypes",
        "milestoneStatistics",
        "milestoneDurations",
    }
    assert all(isinstance(r["index"], int) for r in lists)


def test_a_dict_of_lists_keeps_every_element_and_its_position() -> None:
    payload = {"a": [{"code": "x"}, {"code": "x"}], "b": ["s"], "c": []}
    assert list(iter_records(payload, ("@",))) == [
        {"key": "a", "index": 0, "code": "x"},
        {"key": "a", "index": 1, "code": "x"},
        {"key": "b", "index": 0, "value": "s"},
    ]


def test_dict_of_lists_datasets_are_keyed_by_list_name_and_position() -> None:
    for route in DICT_OF_LISTS:
        ep = BY_NAME[_name(route)]
        assert ep.records == ("@",) and ep.keys == ("key", "index"), route
        table = MlbRecordNormalizer().normalize(ep, _fixture(ep.name))
        pairs = list(
            zip(table.column("key").to_pylist(), table.column("index").to_pylist(), strict=True)
        )
        assert table.num_rows > 0 and len(set(pairs)) == len(pairs), route
        assert table.column("_extras").null_count == table.num_rows, route


def test_each_lookup_fixture_is_unique_on_its_declared_key() -> None:
    for route in LOOKUP_ROUTES:
        ep = BY_NAME[_name(route)]
        table = MlbRecordNormalizer().normalize(ep, _fixture(ep.name))
        cols = [table.column(snake(k)).to_pylist() for k in ep.keys]
        rows = list(zip(*cols, strict=True))
        assert table.num_rows > 0 and len(set(rows)) == len(rows), route


def test_a_list_inside_a_list_is_kept_as_json_text_not_a_python_repr() -> None:
    """Review finding of the Gemini second opinion: ``[["a", "b"]]`` must not become ``"['a', 'b']"``."""
    rows = list(iter_records({"group": [["a", "b"], "c"]}, ("@",)))
    assert [r["value"] for r in rows] == ['["a", "b"]', "c"]
    assert json.loads(str(rows[0]["value"])) == ["a", "b"]
