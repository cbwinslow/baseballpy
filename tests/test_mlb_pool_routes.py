"""A league-wide pool row reads the same whichever route fetched it (``/v1/stats`` or the hydrate fallback).

Shapes are the real ones (measured 2026-11-14, ``stats_expected_statistics_hitting`` 2008): the direct
page has one stats block with ``type``/``group``/``exemptions`` around the splits, the hydrate page has
the same block under each person.
"""

from typing import Any

import pyarrow as pa

from baseballpy.sources import catalog
from baseballpy.sources.mlb_api.generic import MlbRecordNormalizer, stats_payload

DATASET = "stats_expected_statistics_hitting"
#: columns only the direct route can fill: the rank of the split in the pool and the pool echo
DIRECT_ONLY = {"rank", "stats_player_pool"}


def _split(player_id: int) -> dict[str, Any]:
    return {
        "season": "2008",
        "stat": {"avg": ".000", "slg": ".000", "woba": ".073", "wobaCon": ".---"},
        "player": {
            "id": player_id,
            "fullName": "Edgardo Alfonzo",
            "link": f"/api/v1/people/{player_id}",
            "firstName": "Edgardo",
            "lastName": "Alfonzo",
            "primaryPosition": {
                "code": "5",
                "name": "Third Base",
                "type": "Infielder",
                "abbreviation": "3B",
            },
            "nameSlug": f"edgardo-alfonzo-{player_id}",
        },
        "sport": {"id": 11, "link": "/api/v1/sports/11", "name": "Triple A", "abbreviation": "AAA"},
        "gameType": "R",
    }


_BLOCK = {"type": {"displayName": "expectedStatistics"}, "group": {"displayName": "hitting"}}


def _direct(splits: list[dict[str, Any]]) -> dict[str, Any]:
    block = {**_BLOCK, "totalSplits": len(splits), "exemptions": [], "splits": splits}
    return {"copyright": "x", "stats": [block]}


def _hydrate(splits: list[dict[str, Any]]) -> dict[str, Any]:
    people = [
        {
            "id": s["player"]["id"],
            "fullName": "Edgardo Alfonzo",
            "stats": [{**_BLOCK, "exemptions": [], "splits": [s]}],
        }
        for s in splits
    ]
    return {"copyright": "x", "people": people}


def _rows(payload: dict[str, Any]) -> pa.Table:
    catalog.register_all()
    return MlbRecordNormalizer().normalize(DATASET, payload, extra={"sport_id": 11})


def test_a_hydrate_page_and_a_direct_page_give_the_same_typed_row() -> None:
    splits = [_split(110135), _split(110682)]
    direct = _rows(_direct(splits))
    hydrate = _rows(stats_payload(_hydrate(splits)))
    assert direct.num_rows == hydrate.num_rows == 2
    same = [n for n in direct.column_names if n not in DIRECT_ONLY]
    assert direct.select(same).to_pylist() == hydrate.select(same).to_pylist()
    # the two fields the fallback used to leave empty, and the slug that must be typed on both
    assert hydrate["stats_type_display_name"].to_pylist() == ["expectedStatistics"] * 2
    assert hydrate["stats_group_display_name"].to_pylist() == ["hitting"] * 2
    assert hydrate["player_name_slug"].to_pylist() == [
        "edgardo-alfonzo-110135",
        "edgardo-alfonzo-110682",
    ]
    assert hydrate["_extras"].null_count == 2  # nothing is left over for _extras


def test_the_stats_block_fields_survive_the_person_to_stats_conversion() -> None:
    payload = stats_payload(_hydrate([_split(1), _split(2)]))
    block = payload["stats"][0]
    assert block["type"] == {"displayName": "expectedStatistics"}
    assert block["group"] == {"displayName": "hitting"}
    assert block["totalSplits"] == 2
    assert len(block["splits"]) == 2


def test_a_person_without_stat_blocks_does_not_break_the_conversion() -> None:
    """The provider may answer a person with \"stats\": null; that person adds no rows and stops nothing."""
    payload = stats_payload(
        {"people": [{"id": 1, "stats": None}, {"id": 2}] + _hydrate([_split(3)])["people"]}
    )
    assert payload["stats"][0]["totalSplits"] == 1
