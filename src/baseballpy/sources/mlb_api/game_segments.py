"""The MLB per-game download on segments (ADR 95): each URL once, parsed once, all its datasets cut from it.

The 13 per-game datasets come from only five URLs (the live feed feeds four datasets, the boxscore
six). The endpoint registry already says which: endpoints of ``scope="game"`` with the same path are
cut from the same answer (:func:`game_url_groups`), so no list of datasets lives here.

For every game that is not stored yet, :func:`ingest_game_segments` requests each URL once, hands the
responses to a :class:`~baseballpy.core.segments.SegmentWriter` (journal, then parse), and commits a
segment every ``segment_games`` games or ``segment_seconds`` seconds. A game is stored only when every
URL answered 200 with a body that decodes, or answered 404 for a dataset whose endpoint tolerates it
(a cancelled game has no win probability); anything else leaves the game failed, and it is fetched
again on the next run.
"""

import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import msgspec
import pyarrow as pa

from baseballpy.core.config import STATSAPI_HOST
from baseballpy.core.http import HttpStatusError, TransportError
from baseballpy.core.responselog import Response
from baseballpy.core.segments import (
    ROW_GROUP_UNITS,
    DatasetRows,
    SegmentWriter,
)
from baseballpy.sources.mlb_api.endpoints import MLB_BASE_URL, SUPPORTED, MlbEndpoint
from baseballpy.sources.mlb_api.generic import (
    EndpointReport,
    MlbEndpointExtractor,
    MlbRecordNormalizer,
)
from baseballpy.sources.mlb_api.mlb_schema import MLB_SCHEMAS

SEGMENT_GAMES = 250
SEGMENT_SECONDS = 600.0
SOURCE = "mlb_api"


class BadBodyError(ValueError):
    """A response whose body is empty or does not decode: the game is not stored."""


@dataclass(frozen=True)
class UrlGroup:
    """One URL of a game and the datasets cut from its answer."""

    path: str
    params: tuple[tuple[str, str], ...]
    endpoints: tuple[MlbEndpoint, ...]

    @property
    def datasets(self) -> tuple[str, ...]:
        """The dataset names cut from this URL."""
        return tuple(e.name for e in self.endpoints)

    @property
    def tolerates_missing(self) -> bool:
        """True when every dataset of the URL accepts a 404 as "nothing there"."""
        return all(e.tolerate_missing for e in self.endpoints)

    def url(self, game_pk: int) -> str:
        """The request URL of one game."""
        return f"{MLB_BASE_URL}/{self.path.format(game_pk=game_pk)}"


def game_url_groups() -> list[UrlGroup]:
    """The URLs of one game, from the registry: same path (and parameters) means same answer."""
    grouped: dict[tuple[str, tuple[tuple[str, str], ...]], list[MlbEndpoint]] = {}
    for endpoint in SUPPORTED:
        if endpoint.scope != "game" or endpoint.name not in MLB_SCHEMAS:
            continue
        key = (endpoint.path, tuple(sorted((k, str(v)) for k, v in endpoint.params.items())))
        grouped.setdefault(key, []).append(endpoint)
    return [
        UrlGroup(path, params, tuple(sorted(eps, key=lambda e: e.name)))
        for (path, params), eps in sorted(grouped.items())
    ]


def decode_body(body: bytes) -> Any:
    """Decode one response body (the only place a body is decoded); ``BadBodyError`` if it cannot be."""
    if not body.strip():
        raise BadBodyError("empty response body")
    try:
        return msgspec.json.decode(body)
    except msgspec.DecodeError as exc:
        raise BadBodyError(f"response body is not JSON: {exc}") from exc


def game_normalizer(
    normalizer: MlbRecordNormalizer | None = None,
) -> Callable[[str, Sequence[Response]], Mapping[str, DatasetRows]]:
    """The parsing function a :class:`SegmentWriter` needs: one answer in, the rows of its datasets out."""
    use = normalizer or MlbRecordNormalizer()
    groups = game_url_groups()

    def normalize(unit_id: str, responses: Sequence[Response]) -> dict[str, DatasetRows]:
        pk = int(unit_id)
        by_url = {group.url(pk): group for group in groups}
        rows: dict[str, DatasetRows] = {}
        for response in responses:
            group = by_url.get(response.url)
            if group is None:
                raise ValueError(f"game {pk}: no dataset is cut from {response.url}")
            payload = decode_body(response.body) if response.status == 200 else None
            for endpoint in group.endpoints:
                if payload is None:  # a tolerated 404: the game has nothing at this URL
                    table = _empty(endpoint)
                else:
                    table = use.normalize(endpoint, payload, extra={"game_pk": pk})
                rows[endpoint.name] = DatasetRows(table, response.sha256)
        return rows

    return normalize


def _empty(endpoint: MlbEndpoint) -> pa.Table:
    return MLB_SCHEMAS[endpoint.name].empty_table()


@dataclass
class GameSegmentReport:
    """What one call of :func:`ingest_game_segments` did."""

    stored: int = 0
    #: games skipped because they were stored (or journalled) before this call
    already: int = 0
    #: ``{game_pk: why}`` for games that are not stored; they are fetched again next time
    failed: dict[int, str] = field(default_factory=dict)
    segments: int = 0
    #: rows cut per dataset by this call (a game replayed from the journal counts again)
    rows: dict[str, int] = field(default_factory=dict)


MAX_LISTED_FAILURES = 20


def game_segment_reports(report: GameSegmentReport, games: int) -> list[EndpointReport]:
    """The per-dataset :class:`EndpointReport` list the job result expects, from a segment run.

    One report per dataset with its rows, plus one named ``game_segments`` that carries the failed
    games as errors (the first few; the job fails but keeps what was stored).
    """
    names = [name for group in game_url_groups() for name in group.datasets]
    reports = [
        EndpointReport(name, games, report.rows.get(name, 0), report.already)
        for name in sorted(names)
    ]
    errors = [f"game {pk}: {why}" for pk, why in sorted(report.failed.items())]
    if len(errors) > MAX_LISTED_FAILURES:
        errors = [
            *errors[:MAX_LISTED_FAILURES],
            f"... and {len(errors) - MAX_LISTED_FAILURES} more",
        ]
    reports.append(EndpointReport("game_segments", games, 0, report.already, errors=tuple(errors)))
    return reports


def _fetch_game(
    extractor: MlbEndpointExtractor, groups: Sequence[UrlGroup], pk: int
) -> list[Response] | str:
    """Every URL of one game, or the reason the game cannot be stored (nothing is written)."""
    responses: list[Response] = []
    for group in groups:
        url = group.url(pk)
        try:
            result = extractor.http.get_sync(url, allow=(200, 404))
        except (HttpStatusError, TransportError) as exc:
            return f"{url}: {exc}"
        if result.status == 404 and not group.tolerates_missing:
            return f"{url}: HTTP 404"
        if result.status == 200 and not result.content.strip():
            return f"{url}: empty response body"
        responses.append(
            Response(
                url=url,
                body=result.content,
                fetched_at=datetime.now(UTC).isoformat(),
                status=result.status,
                etag=result.etag or "",
            )
        )
    return responses


def ingest_game_segments(
    extractor: MlbEndpointExtractor,
    season: int,
    game_pks: Sequence[int],
    *,
    segment_games: int = SEGMENT_GAMES,
    segment_seconds: float = SEGMENT_SECONDS,
    row_group_units: int = ROW_GROUP_UNITS,
    workers: int | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> GameSegmentReport:
    """Store the per-game datasets of ``game_pks`` as segments; games stored before are skipped.

    Games are fetched by ``workers`` threads (default: the in-flight limit of the host, so the
    HTTP client stays the only gate); writing is done here, one game at a time, in request order.
    """
    groups = game_url_groups()
    report = GameSegmentReport()
    inner = game_normalizer(extractor.normalizer)

    def tally(unit_id: str, responses: Sequence[Response]) -> Mapping[str, DatasetRows]:
        rows = inner(unit_id, responses)
        for name, item in rows.items():
            report.rows[name] = report.rows.get(name, 0) + item.table.num_rows
        return rows

    writer = SegmentWriter(
        extractor.cache_config, SOURCE, season, tally, row_group_units=row_group_units
    )
    stored = writer.stored()
    todo = [pk for pk in game_pks if str(pk) not in stored]
    report.already = len(game_pks) - len(todo)
    size = max(1, workers or extractor.http.limit_for(STATSAPI_HOST))
    open_since = clock()
    open_games = len(
        writer.log.open_units()
    )  # games replayed from the journal belong to this segment

    def commit() -> None:
        nonlocal open_since, open_games
        if writer.commit() is not None:
            report.segments += 1
        open_since, open_games = clock(), 0

    with ThreadPoolExecutor(max_workers=size) as pool:
        waiting: deque[tuple[int, Future[list[Response] | str]]] = deque()
        queue = iter(todo)

        def refill() -> None:
            while len(waiting) < size * 2:
                pk = next(queue, None)
                if pk is None:
                    return
                waiting.append((pk, pool.submit(_fetch_game, extractor, groups, pk)))

        refill()
        while waiting:
            pk, future = waiting.popleft()
            outcome = future.result()
            refill()
            if isinstance(outcome, str):
                report.failed[pk] = outcome
                continue
            try:
                writer.add_unit(str(pk), outcome)
            except BadBodyError as exc:
                report.failed[pk] = str(exc)
                continue
            report.stored += 1
            open_games += 1
            if open_games >= segment_games or clock() - open_since >= segment_seconds:
                commit()
    commit()
    return report
