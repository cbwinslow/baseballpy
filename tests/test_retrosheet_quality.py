"""Retrosheet data-quality checks: duplicate keys and ids that point nowhere (task 5.13)."""

from pathlib import Path

import pyarrow as pa
import respx
from conftest import RetroRepo
from test_retrosheet_coverage import full_season

from baseballpy.cli_ingest import scan_lake
from baseballpy.core.config import LakeConfig
from baseballpy.sources.retrosheet.api import RetrosheetSource
from baseballpy.sources.retrosheet.quality import quality_report


def test_orphan_player_ids_are_reported() -> None:
    events = pa.table(
        {"GAME_ID": ["g", "g", "g"], "EVENT_ID": [1, 2, 3], "BAT_ID": ["a", "b", None]}
    )
    rosters = pa.table({"player_id": ["a"]})
    found = quality_report("events", events, ("GAME_ID", "EVENT_ID"), lambda ref: rosters)
    assert found == {"orphan_rows:BAT_ID->retrosheet.rosters": 1}  # NULL is not an orphan
    # no parent stored: no finding, nothing to compare with
    assert quality_report("events", events, ("GAME_ID", "EVENT_ID"), lambda ref: None) == {}


def test_duplicate_keys_are_counted() -> None:
    table = pa.table({"GAME_ID": ["g", "g", "h"], "EVENT_ID": [1, 1, 1]})
    assert quality_report("events", table, ("GAME_ID", "EVENT_ID"), lambda ref: None) == {
        "duplicate_key_rows": 1
    }


@respx.mock
def test_findings_do_not_depend_on_load_order_and_reach_catalog_status(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    full_season(retro_repo).mount()
    cfg = LakeConfig(home=tmp_path)
    source = RetrosheetSource(cache_config=cfg)
    # events first, rosters last: the check runs after the whole season is stored
    source.ingest_season(2024, datasets=("events", "rosters"))
    entry = cfg.dataset_manifest("retrosheet", "events", "processed").get_chunk(
        "season=2024/events"
    )
    entry = entry or cfg.dataset_manifest("retrosheet", "events", "processed").chunks()["events"]
    # the fixture game has a pitcher (pitch01) that the fixture roster does not list
    assert entry["quality"] == {"orphan_rows:PIT_ID->retrosheet.rosters": 2}
    status = {s.dataset: s for s in scan_lake(cfg) if s.source == "retrosheet"}
    assert status["events"].quality == {"orphan_rows:PIT_ID->retrosheet.rosters": 2}
