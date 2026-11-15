"""The live supervisor (ADR 137, ADR 140): follow every MLB game while it is played and keep its rows in the lake.

One process, one event loop, no new service:

* a **schedule watcher** looks at today's (and yesterday's) schedule every ``schedule_interval_seconds`` and starts a
  task for each game that is live or starts within ``lead_minutes``;
* **one task per game** runs the stream (``GamedayLiveStreamer.stream_live_events``: polling, diffPatch, the journal of
  ADR 138) and puts each event on one bounded queue; when the queue is full the game tasks wait, so a slow disk slows
  polling and memory stays flat;
* **one writer task** drains the queue into per-game buffers and, every ``commit_seconds``, hands each game's new events
  to the sink (``LiveGameSink``: one rewritten file per game, ADR 139) in a thread; a failed write keeps the buffer and
  is retried at the next flush (the journal already holds every answer);
* a game stream that raises is restarted after a pause, at most ``restart_limit`` times, then given up and reported;
  every failure is logged and counted, none is swallowed;
* the memory governor (``core/memguard.py``) decides whether one more game may start; ``max_live_games`` bounds the
  number at once; all requests go through the shared ``HttpClient`` (rate limit, retries, in-flight gate);
* stopping (the ``stop`` event or a cancel) cancels the game tasks, flushes what is buffered and leaves no task behind.

A game stays followed until its stream ends (a terminal status, or the stream's own idle limit). The supervisor does
not start a game twice in one run.
"""

import asyncio
import functools
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

import msgspec
import pyarrow as pa

from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import StreamingConfig
from baseballpy.core.http import HttpStatusError, TransportError
from baseballpy.sources.mlb_api.stream import LiveEvent

logger = logging.getLogger(__name__)

#: what a schedule look or a game stream can fail with and be tried again (anything else is a bug and is logged loudly)
PROVIDER_ERRORS = (
    HttpStatusError,
    TransportError,
    OSError,
    TimeoutError,
    ValueError,
    msgspec.DecodeError,
)
#: what a write to the lake can fail with and be tried again at the next flush
WRITE_ERRORS = (OSError, pa.ArrowException, ValueError)

#: the schedule's abstract state of a game that is over: nothing to follow
OVER_STATES = frozenset({"Final"})


@dataclass(frozen=True)
class ScheduledGame:
    """One game of the schedule, as much as the supervisor needs."""

    game_pk: int
    season: int
    state: str
    start_utc: datetime | None


def is_due(game: ScheduledGame, now: datetime, lead_minutes: int) -> bool:
    """Whether a game should be followed now: not over, and live or starting within ``lead_minutes``."""
    if game.state in OVER_STATES:
        return False
    return game.start_utc is None or game.start_utc - now <= timedelta(minutes=lead_minutes)


class ScheduleSource(Protocol):
    """Where the games of a day come from (the real one asks the MLB schedule; tests script it)."""

    async def games(self, day: date) -> list[ScheduledGame]:
        """Every game scheduled on ``day``."""
        ...


class GameSink(Protocol):
    """Where live rows go (``LiveGameSink``)."""

    def write(self, season: int, game_pk: int, events: Sequence[LiveEvent]) -> int:
        """Merge ``events`` into the game's file; the rows it now holds."""
        ...


class Governor(Protocol):
    """The part of ``MemoryGovernor`` the supervisor uses."""

    def may_start(self, running: int) -> bool:
        """Whether one more game may start now."""
        ...

    def observe(self, running: int) -> None:
        """Sample memory while ``running`` games are followed."""
        ...

    def note_started(self) -> None:
        """A game was just started."""
        ...


StreamFactory = Callable[[int], AsyncIterator[LiveEvent]]


@dataclass
class LiveReport:
    """What one run did."""

    started: int = 0
    finished: int = 0
    restarts: int = 0
    events: int = 0
    write_errors: int = 0
    schedule_errors: int = 0
    failed: list[int] = field(default_factory=list)


class _Marker:
    """A control item on the queue (flush now, stop)."""

    def __init__(self, name: str) -> None:
        self.name = name


_FLUSH = _Marker("flush")
_STOP = _Marker("stop")
_Item = tuple[ScheduledGame, LiveEvent] | _Marker


class LiveSupervisor:
    """Follows games and writes their rows; see the module docstring."""

    def __init__(
        self,
        *,
        sink: GameSink,
        schedule: ScheduleSource,
        stream: StreamFactory,
        config: StreamingConfig | None = None,
        governor: Governor | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] | None = None,
        destination: str = "",
    ) -> None:
        self.sink = sink
        self.schedule = schedule
        self.stream = stream
        self.config = config or StreamingConfig()
        self.governor = governor
        self._now = now
        self._sleep = sleep
        self._destination = destination
        self.report = LiveReport()
        self._seen: set[int] = set()
        self._running: dict[int, asyncio.Task[None]] = {}

    # -- the loop -----------------------------------------------------------------------------

    async def run(self, stop: asyncio.Event) -> LiveReport:
        """Follow games until ``stop`` is set (or the task is cancelled); returns what was done."""
        queue: asyncio.Queue[_Item] = asyncio.Queue(maxsize=max(1, self.config.queue_size))
        async with default_audit_logger.async_track(
            operation="mlb_live",
            source="mlb_api",
            endpoint="schedule+feed/live",
            destination=self._destination,
        ) as tracker:
            writer = asyncio.create_task(self._writer(queue), name="live-writer")
            ticker = asyncio.create_task(self._ticker(queue), name="live-ticker")
            try:
                while not stop.is_set():
                    await self._schedule_pass(queue, stop)
                    if self.governor is not None:
                        self.governor.observe(len(self._running))
                    if stop.is_set():
                        break
                    await self._pause(self.config.schedule_interval_seconds, stop)
            finally:
                await self._shutdown(queue, writer, ticker)
                tracker.set_records(self.report.events)
        return self.report

    async def _shutdown(
        self, queue: asyncio.Queue[_Item], writer: asyncio.Task[None], ticker: asyncio.Task[None]
    ) -> None:
        games = list(self._running.values())
        for task in games:
            task.cancel()
        await asyncio.gather(*games, return_exceptions=True)
        ticker.cancel()
        await asyncio.gather(ticker, return_exceptions=True)
        await queue.put(_STOP)  # the writer flushes what it holds, then ends
        await writer

    async def _pause(self, seconds: float, stop: asyncio.Event | None) -> None:
        """Wait ``seconds``; the real wait ends early when ``stop`` is set."""
        if self._sleep is not None:
            await self._sleep(seconds)
        elif stop is None:
            await asyncio.sleep(seconds)
        else:
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=seconds)

    # -- the schedule watcher -----------------------------------------------------------------

    async def _schedule_pass(self, queue: asyncio.Queue[_Item], stop: asyncio.Event) -> None:
        today = self._now().date()
        games: list[ScheduledGame] = []
        for day in (
            today - timedelta(days=1),
            today,
        ):  # a game that began yesterday (UTC) may still be on
            try:
                games += await self.schedule.games(day)
            except PROVIDER_ERRORS as exc:  # logged and counted; the next pass looks again
                self.report.schedule_errors += 1
                logger.warning("live: the schedule of %s could not be read: %s", day, exc)
        now = self._now()
        for game in games:
            if game.game_pk in self._seen or not is_due(game, now, self.config.lead_minutes):
                continue
            if len(self._running) >= self.config.max_live_games:
                logger.info(
                    "live: game %s waits, %d games are followed", game.game_pk, len(self._running)
                )
                continue
            if self.governor is not None and not self.governor.may_start(len(self._running)):
                logger.info("live: game %s waits for memory", game.game_pk)
                continue
            self._start(game, queue, stop)

    def _start(self, game: ScheduledGame, queue: asyncio.Queue[_Item], stop: asyncio.Event) -> None:
        self._seen.add(game.game_pk)
        self.report.started += 1
        if self.governor is not None:
            self.governor.note_started()
        task = asyncio.create_task(
            self._follow(game, queue, stop), name=f"live-game-{game.game_pk}"
        )
        task.add_done_callback(functools.partial(self._crashed, game.game_pk))
        self._running[game.game_pk] = task
        logger.info("live: following game %s", game.game_pk)

    # -- one game -----------------------------------------------------------------------------

    def _crashed(self, game_pk: int, task: "asyncio.Task[None]") -> None:
        """A game task that ended with an error nobody expected (a bug): say so loudly, count it, go on."""
        if task.cancelled() or task.exception() is None:
            return
        self.report.failed.append(game_pk)
        logger.error("live: game %s: the stream task crashed", game_pk, exc_info=task.exception())

    async def _follow(
        self, game: ScheduledGame, queue: asyncio.Queue[_Item], stop: asyncio.Event
    ) -> None:
        attempts = 0
        try:
            while True:
                try:
                    async for event in self.stream(game.game_pk):
                        await queue.put((game, event))
                    self.report.finished += 1
                    return
                except asyncio.CancelledError:
                    raise
                except PROVIDER_ERRORS as exc:  # restart policy: logged, counted, bounded
                    attempts += 1
                    if attempts > self.config.restart_limit:
                        logger.warning(
                            "live: game %s: stream failed %d times, giving up: %s",
                            game.game_pk,
                            attempts,
                            exc,
                        )
                        self.report.failed.append(game.game_pk)
                        return
                    self.report.restarts += 1
                    logger.warning(
                        "live: game %s: stream error (%s); restart %d of %d",
                        game.game_pk,
                        exc,
                        attempts,
                        self.config.restart_limit,
                    )
                    await self._pause(self.config.restart_backoff_seconds, stop)
        finally:
            self._running.pop(game.game_pk, None)

    # -- the writer ---------------------------------------------------------------------------

    async def _ticker(self, queue: asyncio.Queue[_Item]) -> None:
        """Asks the writer to flush every ``commit_seconds``."""
        sleep = self._sleep or asyncio.sleep
        while True:
            await sleep(self.config.commit_seconds)
            await queue.put(_FLUSH)

    async def _writer(self, queue: asyncio.Queue[_Item]) -> None:
        buffers: dict[int, tuple[ScheduledGame, list[LiveEvent]]] = {}
        while True:
            item = await queue.get()
            if isinstance(item, _Marker):
                await self._flush(buffers)
                if item is _STOP:
                    left = sum(len(events) for _, events in buffers.values())
                    if left:
                        logger.error(
                            "live: %d events were not written to the lake; they are in the journals",
                            left,
                        )
                    return
                continue
            game, event = item
            held = buffers.setdefault(game.game_pk, (game, []))[1]
            held.append(event)
            if len(held) >= max(1, self.config.queue_size):
                await self._flush(
                    buffers
                )  # a bounded buffer: a stuck sink holds the writer, the queue fills, polling waits

    async def _flush(self, buffers: dict[int, tuple[ScheduledGame, list[LiveEvent]]]) -> None:
        for pk, (game, events) in list(buffers.items()):
            if not events:
                continue
            batch = list(events)
            try:
                await asyncio.to_thread(self.sink.write, game.season, pk, batch)
            except (
                WRITE_ERRORS
            ) as exc:  # a full disk or a bad file: keep the buffer, try at the next flush
                self.report.write_errors += 1
                logger.warning(
                    "live: game %s: writing %d events failed (%s); will retry", pk, len(batch), exc
                )
                continue
            del events[: len(batch)]
            self.report.events += len(batch)
