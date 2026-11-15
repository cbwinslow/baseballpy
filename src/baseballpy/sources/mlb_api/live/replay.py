"""Replay a live journal (ADR 138): the same events again, by running the streamer's own code on the recorded answers.

No second implementation of the patching and event rules exists: :class:`ReplayHttp` answers each request of the
streamer with the next journalled answer (and refuses a request that is not the one recorded), so the events, their
order and the resume rules are exactly those of the live run. The replay writes nothing: no journal, no resume state,
no dead letters.
"""

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from baseballpy.core.config import LakeConfig, QuarantineConfig
from baseballpy.core.http import HttpResult, HttpStatusError
from baseballpy.core.quarantine import Quarantine
from baseballpy.sources.mlb_api.live.journal import JournalRecord, LiveJournal, full_url
from baseballpy.sources.mlb_api.stream import GamedayLiveStreamer, LiveEvent


class ReplayDivergedError(RuntimeError):
    """The streamer asked for something other than the next recorded request (the code or the journal changed)."""


class JournalExhaustedError(Exception):
    """The streamer asked for more answers than were recorded: the live run ended there (normal end of a replay)."""


class ReplayHttp:
    """An ``HttpClient`` stand-in that serves the recorded answers in order."""

    def __init__(self, records: Sequence[JournalRecord]) -> None:
        self._records = iter(records)

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        etag: str | None = None,
        allow: tuple[int, ...] = (200,),
        timeout: float | None = None,
    ) -> HttpResult:
        """The next recorded answer, if it is for this request."""
        try:
            record = next(self._records)
        except StopIteration:
            raise JournalExhaustedError from None
        asked = full_url(url, params)
        if record.url != asked:
            raise ReplayDivergedError(
                f"journal record {record.seq} is for {record.url}, the streamer asked for {asked}"
            )
        if record.error:
            raise HttpStatusError(url, record.status)
        return HttpResult(url, record.status, record.body, record.etag, record.status == 304, 0.0)


async def replay_events(config: LakeConfig, game_pk: int) -> AsyncIterator[LiveEvent]:
    """Every event of a game's journal, as the live run emitted them (``received_utc`` is the replay's own time)."""
    records = LiveJournal(config, game_pk, repair=False).records()
    streamer = GamedayLiveStreamer(
        poll_interval=0.0,
        http=ReplayHttp(records),  # type: ignore[arg-type]  # same ``get``; the streamer only calls ``get``
        lake=config,
        quarantine=Quarantine(QuarantineConfig(base_dir=config.home, enabled=False)),
        journal=False,
        persist_state=False,
        audit_operation="mlb_stream_replay",
    )
    try:
        async for event in streamer.stream_live_events(game_pk, resume=False):
            yield event
    except JournalExhaustedError:
        return
