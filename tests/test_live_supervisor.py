"""The live supervisor (ADR 137): a schedule watcher, one task per game, bounded buffering, restarts, a clean stop.

Everything is fake (schedule, event streams, sink, clock), so no network and no real time pass.
"""

import asyncio
import logging
import threading
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from baseballpy.core.audit import AuditLogger
from baseballpy.core.config import AuditConfig, StreamingConfig
from baseballpy.sources.mlb_api.live import supervisor as supervisor_mod
from baseballpy.sources.mlb_api.live.supervisor import LiveSupervisor, ScheduledGame
from baseballpy.sources.mlb_api.stream import LiveEvent

NOW = datetime(2026, 6, 23, 17, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        for _ in range(30):  # let the other tasks run
            await asyncio.sleep(0)


class Schedule:
    """Serves a scripted list of games per pass; sets ``stop`` after ``passes`` looks."""

    def __init__(self, stop: asyncio.Event, passes: int, games: list[list[ScheduledGame]]) -> None:
        self.stop, self.passes, self.script = stop, passes, games
        self.calls: list[date] = []
        self.looks = 0

    async def games(self, day: date) -> list[ScheduledGame]:
        """A look at today's schedule counts as a pass; yesterday's has no games."""
        self.calls.append(day)
        if day != NOW.date():
            return []
        self.looks += 1
        if self.looks >= self.passes:
            self.stop.set()
        return list(self.script[min(self.looks - 1, len(self.script) - 1)])


class Sink:
    def __init__(self, gate: threading.Event | None = None) -> None:
        self.rows: dict[int, list[int]] = {}
        self.writes = 0
        self.gate = gate
        self.fail_first = 0

    def write(self, season: int, game_pk: int, events: Sequence[LiveEvent]) -> int:
        if self.gate is not None:
            self.gate.wait(timeout=5)
        if self.fail_first:
            self.fail_first -= 1
            raise OSError("disk busy")
        self.writes += 1
        self.rows.setdefault(game_pk, []).extend(e.event_index for e in events)
        return len(self.rows[game_pk])


def _game(pk: int, state: str = "Live", start: datetime | None = None) -> ScheduledGame:
    return ScheduledGame(game_pk=pk, season=2026, state=state, start_utc=start or NOW)


def _event(pk: int, index: int) -> LiveEvent:
    return LiveEvent(game_pk=pk, at_bat_index=0, event_index=index, event_kind="pitch")


def _config(**kw: Any) -> StreamingConfig:
    base: dict[str, Any] = {
        "schedule_interval_seconds": 60.0,
        "commit_seconds": 10.0,
        "max_live_games": 20,
        "lead_minutes": 30,
        "queue_size": 50,
        "restart_limit": 2,
        "restart_backoff_seconds": 1.0,
    }
    return StreamingConfig(**{**base, **kw})


def _stream_of(script: dict[int, list[int]], calls: list[int] | None = None) -> Any:
    """A stream factory: the game's scripted event indexes, then the stream ends (the game is over)."""

    async def stream(pk: int) -> AsyncIterator[LiveEvent]:
        if calls is not None:
            calls.append(pk)
        for index in script.get(pk, []):
            yield _event(pk, index)
            await asyncio.sleep(0)

    return stream


async def _run(
    stop: asyncio.Event,
    schedule: Schedule,
    stream: Any,
    sink: Any,
    clock: Clock,
    config: StreamingConfig | None = None,
    governor: Any = None,
) -> Any:
    sup = LiveSupervisor(
        sink=sink,
        schedule=schedule,
        stream=stream,
        config=config or _config(),
        governor=governor,
        now=clock,
        sleep=clock.sleep,
    )
    return await asyncio.wait_for(sup.run(stop), timeout=20)


@pytest.mark.asyncio
async def test_live_and_soon_games_are_followed_and_finished_or_distant_ones_are_not() -> None:
    stop, clock = asyncio.Event(), Clock()
    schedule = Schedule(
        stop,
        passes=3,
        games=[
            [
                _game(1),
                _game(2, "Preview", NOW + timedelta(minutes=20)),
                _game(3, "Final"),
                _game(4, "Preview", NOW + timedelta(hours=5)),
            ]
        ],
    )
    calls: list[int] = []
    sink = Sink()
    report = await _run(stop, schedule, _stream_of({1: [0, 1, 2], 2: [0, 1]}, calls), sink, clock)
    assert sorted(set(calls)) == [1, 2], "the Final game and the game 5 hours away are not followed"
    assert sink.rows == {1: [0, 1, 2], 2: [0, 1]}
    assert report.started == 2 and report.finished == 2 and report.events == 5
    assert not report.failed


@pytest.mark.asyncio
async def test_a_game_that_starts_later_is_picked_up_when_it_comes_within_the_lead_time() -> None:
    stop, clock = asyncio.Event(), Clock()
    later = _game(9, "Preview", NOW + timedelta(minutes=100))
    schedule = Schedule(stop, passes=4, games=[[later]])
    sink = Sink()
    await _run(
        stop, schedule, _stream_of({9: [0]}), sink, clock, _config(schedule_interval_seconds=3600.0)
    )
    assert sink.rows == {9: [0]}, (
        "after enough minutes passed the game was within the 30 minute lead"
    )


@pytest.mark.asyncio
async def test_a_stream_that_fails_is_restarted_then_given_up_and_the_others_go_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop, clock = asyncio.Event(), Clock()
    schedule = Schedule(stop, passes=4, games=[[_game(1), _game(2)]])
    attempts: dict[int, int] = {1: 0, 2: 0}

    async def stream(pk: int) -> AsyncIterator[LiveEvent]:
        attempts[pk] += 1
        if pk == 1:
            raise ConnectionError("feed down")
        yield _event(pk, 0)

    sink = Sink()
    with caplog.at_level(logging.WARNING):
        report = await _run(stop, schedule, stream, sink, clock)
    assert attempts[1] == 3, "one try and restart_limit=2 restarts"
    assert report.failed == [1] and report.restarts == 2
    assert sink.rows == {2: [0]}
    assert any("feed down" in m and "game 1" in m for m in caplog.messages), "never silent"


@pytest.mark.asyncio
async def test_a_stream_that_breaks_in_the_middle_is_restarted_and_all_events_arrive() -> None:
    stop, clock = asyncio.Event(), Clock()
    schedule = Schedule(stop, passes=3, games=[[_game(1)]])
    runs = {"n": 0}

    async def stream(pk: int) -> AsyncIterator[LiveEvent]:
        runs["n"] += 1
        if runs["n"] == 1:
            yield _event(pk, 0)
            raise ConnectionError("reset")
        yield _event(pk, 1)  # the streamer's watermark would skip event 0 on the second run

    sink = Sink()
    report = await _run(stop, schedule, stream, sink, clock)
    assert sink.rows == {1: [0, 1]} and report.restarts == 1 and not report.failed


@pytest.mark.asyncio
async def test_the_memory_gate_holds_a_game_back_until_it_says_yes() -> None:
    class Governor:
        def __init__(self) -> None:
            self.asked = 0

        def may_start(self, running: int) -> bool:
            self.asked += 1
            return self.asked > 2

        def observe(self, running: int) -> None:
            pass

        def note_started(self) -> None:
            pass

    stop, clock = asyncio.Event(), Clock()
    schedule = Schedule(stop, passes=5, games=[[_game(1)]])
    governor = Governor()
    sink = Sink()
    await _run(stop, schedule, _stream_of({1: [0]}), sink, clock, governor=governor)
    assert governor.asked >= 3 and sink.rows == {1: [0]}


@pytest.mark.asyncio
async def test_at_most_max_live_games_are_followed_at_once() -> None:
    stop, clock = asyncio.Event(), Clock()
    schedule = Schedule(stop, passes=2, games=[[_game(1), _game(2), _game(3)]])
    live = {"now": 0, "max": 0}
    release = asyncio.Event()

    async def stream(pk: int) -> AsyncIterator[LiveEvent]:
        live["now"] += 1
        live["max"] = max(live["max"], live["now"])
        try:
            await release.wait()
            yield _event(pk, 0)
        finally:
            live["now"] -= 1

    async def opener() -> None:
        while not stop.is_set():
            await asyncio.sleep(0)
        release.set()

    sink = Sink()
    opener_task = asyncio.create_task(opener())
    await _run(stop, schedule, stream, sink, clock, _config(max_live_games=2))
    await opener_task
    assert live["max"] == 2


@pytest.mark.asyncio
async def test_a_slow_sink_stalls_polling_instead_of_growing_memory() -> None:
    stop, clock = asyncio.Event(), Clock()
    schedule = Schedule(stop, passes=10**9, games=[[_game(1)]])
    gate = threading.Event()
    sink = Sink(gate)
    pulled = {"n": 0}
    checked: list[int] = []

    async def stream(pk: int) -> AsyncIterator[LiveEvent]:
        for index in range(300):
            pulled["n"] += 1
            yield _event(pk, index)

    async def watcher() -> None:
        for _ in range(400):
            await asyncio.sleep(0)
        checked.append(pulled["n"])  # the writer is stuck in the slow sink here
        gate.set()
        for _ in range(600):
            await asyncio.sleep(0)
        stop.set()

    watch = asyncio.create_task(watcher())
    await _run(stop, schedule, stream, sink, clock, _config(queue_size=10, max_live_games=1))
    await watch
    assert checked and checked[0] < 60, f"polling must stall behind a full queue, pulled {checked}"
    assert sink.rows[1] == list(range(300)), "after the sink recovers: order kept, nothing lost"


@pytest.mark.asyncio
async def test_a_failed_write_is_retried_and_no_event_is_lost(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop, clock = asyncio.Event(), Clock()
    schedule = Schedule(stop, passes=3, games=[[_game(1)]])
    sink = Sink()
    sink.fail_first = 1
    with caplog.at_level(logging.WARNING):
        report = await _run(stop, schedule, _stream_of({1: [0, 1, 2]}), sink, clock)
    assert sink.rows == {1: [0, 1, 2]}
    assert report.write_errors == 1 and any("disk busy" in m for m in caplog.messages)


@pytest.mark.asyncio
async def test_stopping_flushes_what_is_buffered_and_leaves_no_task_behind() -> None:
    stop, clock = asyncio.Event(), Clock()
    schedule = Schedule(stop, passes=2, games=[[_game(1)]])

    async def stream(pk: int) -> AsyncIterator[LiveEvent]:
        yield _event(pk, 0)
        yield _event(pk, 1)
        await asyncio.sleep(3600)  # a long quiet stretch of the game
        yield _event(pk, 2)

    sink = Sink()
    before = len(asyncio.all_tasks())
    report = await _run(stop, schedule, stream, sink, clock)
    assert sink.rows == {1: [0, 1]} and report.events == 2
    assert len(asyncio.all_tasks()) == before


@pytest.mark.asyncio
async def test_a_schedule_error_is_logged_and_the_next_look_works(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop, clock = asyncio.Event(), Clock()
    inner = Schedule(stop, passes=3, games=[[_game(1)]])
    state = {"first": True}

    class Flaky:
        calls = inner.calls

        async def games(self, day: date) -> list[ScheduledGame]:
            if state["first"]:
                state["first"] = False
                raise ConnectionError("schedule down")
            return await inner.games(day)

    sink = Sink()
    with caplog.at_level(logging.WARNING):
        report = await _run(stop, Flaky(), _stream_of({1: [0]}), sink, clock)  # type: ignore[arg-type]
    assert sink.rows == {1: [0]} and report.schedule_errors == 1
    assert any("schedule down" in m for m in caplog.messages)


@pytest.mark.asyncio
async def test_the_audit_log_records_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit = AuditLogger(AuditConfig(base_dir=tmp_path))
    monkeypatch.setattr(supervisor_mod, "default_audit_logger", audit)
    stop, clock = asyncio.Event(), Clock()
    schedule = Schedule(stop, passes=2, games=[[_game(1)]])
    await _run(stop, schedule, _stream_of({1: [0, 1]}), Sink(), clock)
    lines = [
        x for x in audit.log_path.read_text(encoding="utf-8").splitlines() if '"mlb_live"' in x
    ]
    assert len(lines) == 1 and '"records_count":2' in lines[0].replace(" ", "")


@pytest.mark.asyncio
async def test_an_unexpected_error_is_logged_loudly_the_game_is_failed_and_the_others_go_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A bug (here a KeyError) is not retried like a network error: it is logged with its traceback and counted."""
    stop, clock = asyncio.Event(), Clock()
    schedule = Schedule(stop, passes=3, games=[[_game(1), _game(2)]])

    async def stream(pk: int) -> AsyncIterator[LiveEvent]:
        if pk == 1:
            raise KeyError("a bug")
        yield _event(pk, 0)

    sink = Sink()
    with caplog.at_level(logging.ERROR):
        report = await _run(stop, schedule, stream, sink, clock)
    assert report.failed == [1] and report.restarts == 0 and sink.rows == {2: [0]}
    assert any("crashed" in r.message and r.exc_info for r in caplog.records)
