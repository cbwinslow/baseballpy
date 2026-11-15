"""Live game rows in the lake (ADR 137): readable mid-game, rewritten whole, never doubled, same schema as history."""

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baseballpy.access import read
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.database import BaseballDatabase
from baseballpy.layout_audit import audit_layout
from baseballpy.sources import catalog
from baseballpy.sources.mlb_api.live.sink import LiveGameSink
from baseballpy.sources.mlb_api.stream import LiveEvent

SEASON = 2026
DATASET = ("mlb_api", "game_live_events")


def _pitch(index: int, speed: float = 95.0) -> dict[str, Any]:
    return {
        "index": index,
        "isPitch": True,
        "playId": f"p{index}",
        "startTime": f"2026-06-23T18:00:{index:02d}.250Z",
        "details": {"type": {"code": "FF"}, "call": {"code": "B"}, "description": "Ball"},
        "pitchData": {"startSpeed": speed, "zone": 11, "coordinates": {"pX": 0.5, "pZ": 3.0}},
        "count": {"balls": 1, "strikes": 0, "outs": 0},
    }


def _events(game_pk: int, indexes: range) -> list[LiveEvent]:
    play = {
        "about": {"atBatIndex": 0, "inning": 1, "isTopInning": True},
        "matchup": {"batter": {"id": 1}, "pitcher": {"id": 2}},
        "result": {"event": "Walk"},
        "count": {"balls": 4, "strikes": 0, "outs": 0},
    }
    return [
        LiveEvent(
            game_pk=game_pk,
            at_bat_index=0,
            event_index=i,
            event_kind="pitch",
            is_pitch=True,
            raw_play=play,
            raw_event=_pitch(i),
        )
        for i in indexes
    ]


@pytest.fixture
def lake(tmp_path: Path) -> LakeConfig:
    catalog.register_all()
    return LakeConfig(home=tmp_path)


def _rows(lake: LakeConfig, sql: str = "SELECT count(*) FROM mlb_live_play_events") -> Any:
    con = BaseballDatabase(cache_config=lake).connect()  # a read-write connect syncs the views
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_the_live_dataset_is_registered_with_the_schema_of_the_history_table() -> None:
    catalog.register_all()
    live = get_dataset(*DATASET)
    history = get_dataset("mlb_api", "game_feed_play_events")
    assert live.schema.equals(history.schema) and live.keys == history.keys
    assert live.view == "mlb_live_play_events" and live.partition == "season"


def test_rows_are_readable_mid_game_and_grow_without_double_counting(lake: LakeConfig) -> None:
    sink = LiveGameSink(lake)
    assert sink.write(SEASON, 7, _events(7, range(0, 3))) == 3
    assert _rows(lake) == [(3,)]
    assert sink.write(SEASON, 7, _events(7, range(3, 5))) == 5
    assert _rows(lake) == [(5,)]
    table = read("mlb_api.game_live_events", seasons=SEASON, backend="pyarrow", config=lake)
    assert table.num_rows == 5


def test_a_restart_that_sends_the_same_events_again_does_not_double_count(lake: LakeConfig) -> None:
    LiveGameSink(lake).write(SEASON, 8, _events(8, range(0, 4)))
    after_restart = LiveGameSink(lake)  # a new process: it knows only the file
    assert after_restart.write(SEASON, 8, _events(8, range(2, 6))) == 6
    assert _rows(lake, "SELECT count(*), count(DISTINCT index) FROM mlb_live_play_events") == [
        (6, 6)
    ]


def test_games_are_separate_files_and_a_game_rewrite_leaves_the_others_alone(
    lake: LakeConfig,
) -> None:
    sink = LiveGameSink(lake)
    sink.write(SEASON, 1, _events(1, range(0, 2)))
    sink.write(SEASON, 2, _events(2, range(0, 3)))
    folder = lake.processed_dir(*DATASET, SEASON)
    assert sorted(p.name for p in folder.glob("*.parquet")) == ["live-1.parquet", "live-2.parquet"]
    before = (folder / "live-1.parquet").read_bytes()
    sink.write(SEASON, 2, _events(2, range(3, 4)))
    assert (folder / "live-1.parquet").read_bytes() == before
    assert _rows(
        lake, "SELECT game_pk, count(*) FROM mlb_live_play_events GROUP BY 1 ORDER BY 1"
    ) == [
        (1, 2),
        (2, 4),
    ]


def test_the_file_has_exactly_the_registered_columns(lake: LakeConfig) -> None:
    LiveGameSink(lake).write(SEASON, 3, _events(3, range(0, 2)))
    path = lake.processed_dir(*DATASET, SEASON) / "live-3.parquet"
    assert pq.read_schema(path).equals(get_dataset(*DATASET).schema, check_metadata=False)


def test_a_write_that_fails_leaves_the_old_file_whole_and_no_part_file(
    lake: LakeConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    sink = LiveGameSink(lake)
    sink.write(SEASON, 4, _events(4, range(0, 3)))
    folder = lake.processed_dir(*DATASET, SEASON)
    before = (folder / "live-4.parquet").read_bytes()

    def boom(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(pq, "write_table", boom)
    with pytest.raises(OSError, match="disk full"):
        sink.write(SEASON, 4, _events(4, range(3, 5)))
    monkeypatch.undo()
    assert (folder / "live-4.parquet").read_bytes() == before
    assert not list(folder.glob("*.part"))
    assert _rows(lake) == [(3,)]


def test_play_result_and_status_events_add_no_rows(lake: LakeConfig) -> None:
    status = LiveEvent(game_pk=5, at_bat_index=-1, event_index=0, event_kind="game_status")
    assert LiveGameSink(lake).write(SEASON, 5, [status, *_events(5, range(0, 2))]) == 2


def test_many_live_files_are_a_normal_layout(lake: LakeConfig) -> None:
    sink = LiveGameSink(lake)
    for game in range(100, 115):
        sink.write(SEASON, game, _events(game, range(0, 1)))
    assert audit_layout(lake, ("mlb_api",)) == []


def test_an_empty_write_creates_no_file(lake: LakeConfig) -> None:
    assert LiveGameSink(lake).write(SEASON, 6, []) == 0
    assert not lake.processed_dir(*DATASET, SEASON).exists()


def test_the_empty_table_type_is_the_registered_one() -> None:
    catalog.register_all()
    assert isinstance(get_dataset(*DATASET).schema.empty_table(), pa.Table)
