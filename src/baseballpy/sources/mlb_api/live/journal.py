"""The live journal (ADR 138): every poll answer of a live game, on disk before the streamer uses it.

One file per game, ``raw/<source>/_live/<game_pk>.journal.zst`` (the leading underscore hides the folder from the
readers, the converter and the layout audit, like ``_open``). It reuses the record format of the response log
(``core/responselog.py``, ADR 95): one record is a header (compressed size, original size, crc32) and one zstd frame,
appended and flushed with ``fsync`` before :meth:`LiveJournal.append` returns. A record that is cut short or does not
match its crc ends the replay; it is logged as a warning and the file is cut back to the last whole record, so new
records follow whole ones.

A record is one answer of the provider: ``url`` (with its query), ``status``, ``etag``, the body bytes and when it
was fetched. A status the HTTP client refuses (``HttpStatusError``) is kept too, flagged ``error``, because it changes
what the streamer does next and a replay must do the same.
"""

import asyncio
import logging
import os
import re
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from baseballpy.core.config import LakeConfig
from baseballpy.core.http import HttpClient, HttpResult, HttpStatusError
from baseballpy.core.responselog import Response, encode_record, read_journal

logger = logging.getLogger(__name__)

SOURCE = "mlb_api"
#: marks a record whose request raised ``HttpStatusError`` (the status is in ``status``, the body is empty)
ERROR_MARK = "!error"
_GAME_URL = re.compile(r"/game/(\d+)/")


@dataclass(frozen=True)
class JournalRecord:
    """One journalled answer, in the order it arrived."""

    seq: int
    url: str
    status: int
    body: bytes
    etag: str | None
    error: bool
    fetched_at: str


def full_url(url: str, params: Mapping[str, Any] | None) -> str:
    """``url`` with its query in a fixed order, so the same request has the same text in a journal and a replay."""
    return f"{url}?{urlencode(sorted((k, str(v)) for k, v in params.items()))}" if params else url


def game_pk_of(url: str) -> int | None:
    """The game a feed URL belongs to (``/game/<pk>/...``), or ``None``."""
    match = _GAME_URL.search(url)
    return int(match.group(1)) if match else None


class LiveJournal:
    """The journal of one game: open it, :meth:`append` answers, read them back with :meth:`records`."""

    def __init__(
        self, config: LakeConfig, game_pk: int, source: str = SOURCE, *, repair: bool = True
    ) -> None:
        self.game_pk = game_pk
        self.path = config.live_journal_path(source, game_pk)
        units, good = read_journal(self.path)
        if self.path.exists() and self.path.stat().st_size != good:
            logger.warning(
                "live journal %s: torn record cut (%d bytes kept, %d dropped)",
                self.path,
                good,
                self.path.stat().st_size - good,
            )
            if repair:  # a replay only reads: it warns and leaves the file as it is
                with self.path.open("r+b") as handle:
                    handle.truncate(good)
                    handle.flush()
                    os.fsync(handle.fileno())
        self._records = [self._record(unit_id, answers) for unit_id, answers in units.items()]
        self._next = 1 + max((r.seq for r in self._records), default=-1)

    @staticmethod
    def _record(unit_id: str, answers: list[Response]) -> JournalRecord:
        answer = answers[0]
        return JournalRecord(
            seq=int(unit_id),
            url=answer.url,
            status=answer.status,
            body=answer.body,
            etag=None if answer.etag in ("", ERROR_MARK) else answer.etag,
            error=answer.etag == ERROR_MARK,
            fetched_at=answer.fetched_at,
        )

    def records(self) -> list[JournalRecord]:
        """Every whole record, in order (a copy)."""
        return list(self._records)

    def append(
        self, url: str, status: int, body: bytes, etag: str | None, *, error: bool = False
    ) -> int:
        """Write one answer and flush it to disk; returns its sequence number."""
        seq = self._next
        fetched_at = datetime.now(UTC).isoformat()
        stored_etag = ERROR_MARK if error else (etag or "")
        record = encode_record(
            f"{seq:010d}", [Response(url, body, fetched_at, status, stored_etag)]
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as handle:
            handle.write(record)
            handle.flush()
            os.fsync(handle.fileno())
        self._records.append(
            JournalRecord(seq, url, status, body, etag if not error else None, error, fetched_at)
        )
        self._next = seq + 1
        return seq


class JournalingHttp:
    """Wraps the shared :class:`HttpClient`: each answer about a game is journalled before it is returned.

    Requests that name no game pass through unchanged. The rate limit, retries and the in-flight gate stay in the
    wrapped client. The write runs in a thread so a slow disk never blocks the event loop.
    """

    def __init__(self, inner: HttpClient, config: LakeConfig, source: str = SOURCE) -> None:
        self.inner = inner
        self.config = config
        self.source = source
        self._journals: dict[int, LiveJournal] = {}

    def journal(self, game_pk: int) -> LiveJournal:
        """The (cached) journal of a game."""
        if game_pk not in self._journals:
            self._journals[game_pk] = LiveJournal(self.config, game_pk, self.source)
        return self._journals[game_pk]

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
        """Same as ``HttpClient.get``, with the answer (or the refused status) kept first."""
        game_pk = game_pk_of(url)
        if game_pk is None:
            return await self.inner.get(
                url, params=params, headers=headers, etag=etag, allow=allow, timeout=timeout
            )
        journal = self.journal(game_pk)
        try:
            result = await self.inner.get(
                url, params=params, headers=headers, etag=etag, allow=allow, timeout=timeout
            )
        except HttpStatusError as exc:
            await asyncio.to_thread(
                journal.append, full_url(url, params), exc.status, b"", None, error=True
            )
            raise
        await asyncio.to_thread(
            journal.append, full_url(url, params), result.status, result.content, result.etag
        )
        return result

    def forget(self, game_pk: int) -> None:
        """Drop the cached journal of a game that has ended."""
        with suppress(KeyError):
            del self._journals[game_pk]
