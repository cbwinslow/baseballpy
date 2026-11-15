"""The JSONL broadcast: every live event as one whole line in a file any program can follow."""

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from baseballpy.core.config import StreamingConfig
from baseballpy.sources.mlb_api.live.broadcast import JsonlBroadcast
from baseballpy.sources.mlb_api.live.supervisor import LiveSupervisor, ScheduledGame
from baseballpy.sources.mlb_api.stream import LiveEvent

NOW = datetime(2026, 6, 23, 17, 0, tzinfo=UTC)


def _event(pk: int, index: int) -> LiveEvent:
    return LiveEvent(
        game_pk=pk, at_bat_index=0, event_index=index, event_kind="pitch", start_speed=95.5
    )


def test_each_event_is_one_whole_json_line_and_the_file_is_appended_never_truncated(
    tmp_path: Path,
) -> None:
    path = tmp_path / "out" / "live.jsonl"
    first = JsonlBroadcast(path)
    first.write(2026, _event(1, 0))
    first.write(2026, _event(1, 1))
    first.close()
    again = JsonlBroadcast(path)  # a restart appends to the same file
    again.write(2026, _event(2, 0))
    again.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines]
    assert [(r["game_pk"], r["event_index"]) for r in rows] == [(1, 0), (1, 1), (2, 0)]
    assert rows[0]["season"] == 2026 and rows[0]["start_speed"] == 95.5
    assert "raw_play" not in rows[0], "the typed fields only, like LiveEvent.to_dict"


def test_a_line_is_on_disk_when_write_returns(tmp_path: Path) -> None:
    path = tmp_path / "live.jsonl"
    broadcast = JsonlBroadcast(path)
    broadcast.write(2026, _event(1, 0))
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1, "a follower sees it at once"
    broadcast.close()


@pytest.mark.asyncio
async def test_the_supervisor_broadcasts_every_event_as_it_arrives(tmp_path: Path) -> None:
    stop = asyncio.Event()
    looks = {"n": 0}

    class Schedule:
        async def games(self, day: date) -> list[ScheduledGame]:
            if day != NOW.date():
                return []
            looks["n"] += 1
            if looks["n"] >= 3:
                stop.set()
            return [ScheduledGame(1, 2026, "Live", NOW)]

    class Sink:
        def write(self, season: int, game_pk: int, events: Sequence[LiveEvent]) -> int:
            return len(events)

    async def stream(pk: int) -> AsyncIterator[LiveEvent]:
        for index in range(3):
            yield _event(pk, index)

    async def sleep(seconds: float) -> None:
        for _ in range(30):
            await asyncio.sleep(0)

    path = tmp_path / "live.jsonl"
    broadcast = JsonlBroadcast(path)
    supervisor = LiveSupervisor(
        sink=Sink(),
        schedule=Schedule(),
        stream=stream,
        config=StreamingConfig(commit_seconds=1000.0),
        now=lambda: NOW,
        sleep=sleep,
        broadcast=broadcast,
    )
    await asyncio.wait_for(supervisor.run(stop), timeout=20)
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert [(r["game_pk"], r["event_index"]) for r in rows] == [(1, 0), (1, 1), (1, 2)]
    assert supervisor.report.events == 3
