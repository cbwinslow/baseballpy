"""The open-games view and the clean-up of stored games (ADR 137): no double count, nothing deleted for the numbers."""

# ruff: noqa: S608 - the SQL below is built from the constant view name OPEN, never from input

import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.database import BaseballDatabase
from baseballpy.sources import catalog
from baseballpy.sources.mlb_api.live.sink import LiveGameSink
from baseballpy.sources.mlb_api.stream import LiveEvent

SEASON = 2026
OPEN = "mlb_game_live_events_open"
#: ruff S608 flags SQL built from text; here the view name is a constant of this file


def _events(game_pk: int, count: int) -> list[LiveEvent]:
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
            raw_event={"index": i, "isPitch": True, "details": {"description": "Ball"}},
        )
        for i in range(count)
    ]


def _store(lake: LakeConfig, dataset: str, games: dict[int, int]) -> None:
    """What the normal finished-game ingest leaves: rows of these games in a history dataset."""
    spec = get_dataset("mlb_api", dataset)
    pks = [pk for pk, n in games.items() for _ in range(n)]
    columns: dict[str, Any] = {f.name: pa.nulls(len(pks), f.type) for f in spec.schema}
    columns["game_pk"] = pa.array(pks, spec.schema.field("game_pk").type)
    if "index" in columns:
        columns["index"] = pa.array(
            [i for n in games.values() for i in range(n)], spec.schema.field("index").type
        )
    folder = lake.processed_dir("mlb_api", dataset, SEASON, create=True)
    pq.write_table(pa.table(columns, schema=spec.schema), folder / "part-stored.parquet")


@pytest.fixture
def lake(tmp_path: Path) -> LakeConfig:
    catalog.register_all()
    return LakeConfig(home=tmp_path)


def _q(lake: LakeConfig, sql: str) -> Any:
    con = BaseballDatabase(cache_config=lake).connect()  # a read-write connect syncs the views
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_with_nothing_stored_every_live_game_is_open(lake: LakeConfig) -> None:
    sink = LiveGameSink(lake)
    sink.write(SEASON, 1, _events(1, 2))
    sink.write(SEASON, 2, _events(2, 3))
    assert _q(lake, f"SELECT game_pk, count(*) FROM {OPEN} GROUP BY 1 ORDER BY 1") == [
        (1, 2),
        (2, 3),
    ]


def test_a_stored_game_leaves_the_open_view_and_the_others_stay(lake: LakeConfig) -> None:
    sink = LiveGameSink(lake)
    sink.write(SEASON, 1, _events(1, 2))
    sink.write(SEASON, 2, _events(2, 3))
    assert _q(lake, f"SELECT count(*) FROM {OPEN}") == [(5,)]
    _store(lake, "game_feed_plays", {1: 1})  # the normal ingest stored game 1
    assert _q(lake, f"SELECT game_pk, count(*) FROM {OPEN} GROUP BY 1 ORDER BY 1") == [(2, 3)]
    assert _q(lake, "SELECT count(*) FROM mlb_game_live_events") == [(5,)], (
        "the live table keeps its rows"
    )


def test_history_plus_open_never_counts_a_game_twice(lake: LakeConfig) -> None:
    sink = LiveGameSink(lake)
    sink.write(SEASON, 1, _events(1, 2))
    sink.write(SEASON, 2, _events(2, 3))
    _store(lake, "game_feed_plays", {1: 1})
    _store(lake, "game_feed_play_events", {1: 2})  # game 1 as stored: two pitch events
    rows = _q(
        lake,
        "SELECT game_pk, count(*) FROM ("
        "SELECT game_pk FROM mlb_game_feed_play_events "
        f"UNION ALL BY NAME SELECT game_pk FROM {OPEN}) GROUP BY 1 ORDER BY 1",
    )
    assert rows == [(1, 2), (2, 3)], "game 1 from history only, game 2 from the open view only"


def test_a_game_that_is_not_stored_yet_stays_open_after_a_crash(lake: LakeConfig) -> None:
    LiveGameSink(lake).write(SEASON, 7, _events(7, 2))
    _store(lake, "game_feed_plays", {8: 1})  # another game was stored; game 7's ingest never ran
    assert _q(lake, f"SELECT game_pk FROM {OPEN} GROUP BY 1") == [(7,)]


def test_the_prune_removes_only_stored_games_older_than_the_limit(lake: LakeConfig) -> None:
    sink = LiveGameSink(lake)
    for game in (1, 2, 3):
        sink.write(SEASON, game, _events(game, 2))
    _store(lake, "game_feed_plays", {1: 1, 2: 1})
    old = time.time() - 10 * 86400
    for game in (1, 3):  # game 1 stored and old, game 3 old but not stored, game 2 stored but fresh
        os.utime(sink.path(SEASON, game), (old, old))
    before = _q(lake, f"SELECT game_pk, count(*) FROM {OPEN} GROUP BY 1 ORDER BY 1")
    removed = sink.prune(SEASON, older_than_days=7, now=datetime.now(UTC))
    assert removed == [1]
    assert sorted(p.name for p in sink.path(SEASON, 1).parent.glob("live-*.parquet")) == [
        "live-2.parquet",
        "live-3.parquet",
    ]
    assert (
        _q(lake, f"SELECT game_pk, count(*) FROM {OPEN} GROUP BY 1 ORDER BY 1")
        == before
        == [(3, 2)]
    ), "the open view is the same before and after the prune"


def test_a_prune_with_no_stored_data_removes_nothing(lake: LakeConfig) -> None:
    sink = LiveGameSink(lake)
    sink.write(SEASON, 1, _events(1, 1))
    os.utime(sink.path(SEASON, 1), (0, 0))
    assert sink.prune(SEASON, older_than_days=1, now=datetime.now(UTC)) == []
    assert sink.path(SEASON, 1).exists()
