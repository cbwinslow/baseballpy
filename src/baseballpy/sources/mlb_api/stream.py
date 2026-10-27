"""Live MLB Gameday streaming: ``timestamps`` + ``diffPatch`` polling, status lifecycle, resumable.

Per poll the streamer asks ``/feed/live/timestamps`` whether the game changed, fetches only the JSON
patch between the last applied timestamp and the newest one (``/feed/live/diffPatch``) and applies it to
a local copy of the feed; it falls back to the full feed (ETag / ``metaData.timeStamp`` comparison) when
a patch is unavailable or does not reproduce the announced timestamp. New content is emitted as
:class:`LiveEvent` objects keyed ``(game_pk, at_bat_index, event_index)``; a watermark persisted under
``cache/stream`` lets a later stream of the same game resume without re-emitting anything.
"""

import asyncio
import copy
import json
import logging
import time
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import msgspec
import pyarrow as pa

from baseballpy.core.atomic import atomic_write
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LakeConfig, StreamingConfig
from baseballpy.core.http import HttpClient, HttpStatusError, get_http_client
from baseballpy.core.quarantine import Quarantine, get_quarantine

logger = logging.getLogger(__name__)

MLB_FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
#: Abstract/detailed states after which no further events will arrive in this stream.
TERMINAL_STATES = frozenset(
    {"Final", "Game Over", "Completed Early", "Postponed", "Cancelled", "Suspended"}
)
WAITING_STATES = frozenset({"Preview", "Pre-Game", "Warmup", "Scheduled"})
DELAYED_POLL_SECONDS = 30.0
_SUBSTITUTIONS = frozenset(
    {
        "offensive_substitution",
        "defensive_substitution",
        "pitching_substitution",
        "defensive_switch",
    }
)


class PatchError(ValueError):
    """A JSON patch could not be applied to the local feed copy (forces a full-feed resync)."""


class LiveEvent(msgspec.Struct, frozen=True, kw_only=True):
    """One discrete live event. ``(game_pk, at_bat_index, event_index)`` is its idempotency key."""

    game_pk: int
    at_bat_index: int
    event_index: int
    # pitch|pickoff|stolen_base|substitution|action|play_result|half_inning_end|game_status
    event_kind: str
    play_id: str | None = None
    is_pitch: bool = False
    pitch_type: str | None = None
    start_speed: float | None = None
    end_speed: float | None = None
    sz_top: float | None = None
    sz_bottom: float | None = None
    px: float | None = None
    pz: float | None = None
    x: float | None = None
    y: float | None = None
    zone: int | None = None
    spin_rate: float | None = None
    spin_direction: float | None = None
    break_angle: float | None = None
    break_length: float | None = None
    break_y: float | None = None
    plate_time: float | None = None
    extension: float | None = None
    launch_speed: float | None = None
    launch_angle: float | None = None
    total_distance: float | None = None
    trajectory: str | None = None
    hardness: str | None = None
    location: str | None = None
    description: str = ""
    call_code: str | None = None
    event: str | None = None
    event_type: str | None = None
    batter_id: int = 0
    pitcher_id: int = 0
    inning: int = 1
    is_top_inning: bool = True
    outs: int = 0
    balls: int = 0
    strikes: int = 0
    play_result: str | None = None
    timestamp: str | None = None
    ts_utc: int | None = None  # microseconds since the epoch (UTC)
    received_utc: int = 0  # microseconds since the epoch (UTC)
    raw_play: dict[str, Any] = msgspec.field(default_factory=dict)
    raw_event: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Flat dict of the typed fields (the raw play/event payloads are left out)."""
        out: dict[str, Any] = msgspec.structs.asdict(self)
        out.pop("raw_play")
        out.pop("raw_event")
        return out


def to_arrow(events: list[LiveEvent]) -> pa.Table:
    """Pitch/action events as a ``game_feed_play_events`` table (live and historical share a schema).

    Rebuilds the live-feed shape around each event so the *same* flattener and strict schema used for
    historical ingestion applies; ``play_result``/``game_status`` events have no ``playEvents`` entry
    and are not included.
    """
    from baseballpy.sources.mlb_api.generic import MlbRecordNormalizer

    normalizer = MlbRecordNormalizer()
    tables = []
    for event in events:
        if event.raw_event is None:
            continue
        play = {**event.raw_play, "playEvents": [event.raw_event]}
        payload = {"liveData": {"plays": {"allPlays": [play]}}}
        tables.append(
            normalizer.normalize("game_feed_play_events", payload, extra={"game_pk": event.game_pk})
        )
    if not tables:
        return normalizer.normalize("game_feed_play_events", {})
    return pa.concat_tables(tables)


# ------------------------------------------------------------------------------------ JSON patch


def _pointer(path: str) -> list[str]:
    if path == "":
        return []
    if not path.startswith("/"):
        raise PatchError(f"bad JSON pointer {path!r}")
    return [p.replace("~1", "/").replace("~0", "~") for p in path[1:].split("/")]


def _resolve(doc: Any, tokens: list[str]) -> Any:
    node = doc
    for token in tokens:
        try:
            node = node[int(token)] if isinstance(node, list) else node[token]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise PatchError(f"path /{'/'.join(tokens)} does not exist") from exc
    return node


def _add(doc: Any, tokens: list[str], value: Any) -> Any:
    if not tokens:
        return value
    parent = _resolve(doc, tokens[:-1])
    key = tokens[-1]
    if isinstance(parent, list):
        index = len(parent) if key == "-" else int(key)
        if index > len(parent):
            raise PatchError(f"index {index} out of range")
        parent.insert(index, value)
    elif isinstance(parent, dict):
        parent[key] = value
    else:
        raise PatchError("cannot add into a scalar")
    return doc


def _remove(doc: Any, tokens: list[str]) -> None:
    parent = _resolve(doc, tokens[:-1])
    key = tokens[-1]
    try:
        if isinstance(parent, list):
            del parent[int(key)]
        else:
            del parent[key]
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise PatchError(f"cannot remove /{'/'.join(tokens)}") from exc


def apply_patch(doc: Any, ops: list[dict[str, Any]]) -> Any:
    """Apply RFC 6902 operations (``add/remove/replace/move/copy/test``) to ``doc`` in place."""
    for op in ops:
        kind = op.get("op")
        tokens = _pointer(str(op.get("path", "")))
        if kind == "add":
            doc = _add(doc, tokens, copy.deepcopy(op["value"]))
        elif kind == "remove":
            _remove(doc, tokens)
        elif kind == "replace":
            _resolve(doc, tokens)  # must exist
            if not tokens:
                doc = copy.deepcopy(op["value"])
            else:
                parent = _resolve(doc, tokens[:-1])
                value = copy.deepcopy(op["value"])
                if isinstance(parent, list):
                    parent[int(tokens[-1])] = value
                else:
                    parent[tokens[-1]] = value
        elif kind == "copy":
            value = copy.deepcopy(_resolve(doc, _pointer(str(op["from"]))))
            doc = _add(doc, tokens, value)
        elif kind == "move":
            source = _pointer(str(op["from"]))
            value = _resolve(doc, source)
            _remove(doc, source)
            doc = _add(doc, tokens, value)
        elif kind == "test":
            if _resolve(doc, tokens) != op.get("value"):
                raise PatchError(f"test failed at {op.get('path')}")
        else:
            raise PatchError(f"unsupported patch op {kind!r}")
    return doc


def patch_ops(payload: Any) -> list[dict[str, Any]]:
    """Operations of a ``diffPatch`` response (a list of ``{"diff": [...]}`` or one such object)."""
    entries = payload if isinstance(payload, list) else [payload]
    ops: list[dict[str, Any]] = []
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("diff"), list):
            ops.extend(entry["diff"])
        elif isinstance(entry, dict) and "op" in entry:
            ops.append(entry)
        elif entry not in ({}, [], None):
            raise PatchError("unrecognised diffPatch payload")
    return ops


# ------------------------------------------------------------------------------------ events


def _micros(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return int(stamp.timestamp() * 1_000_000)


def _kind(event: dict[str, Any]) -> str:
    details = event.get("details", {})
    etype = str(details.get("eventType") or "")
    if event.get("isPitch"):
        return "pitch"
    if etype.startswith("pickoff"):
        return "pickoff"
    if "stolen_base" in etype:
        return "stolen_base"
    if etype in _SUBSTITUTIONS or "substitution" in str(details.get("event", "")).lower():
        return "substitution"
    return "action"


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def build_event(
    game_pk: int,
    play: dict[str, Any],
    event: dict[str, Any],
    received_utc: int,
) -> LiveEvent:
    """A :class:`LiveEvent` of one ``playEvents`` entry with its plate appearance's context."""
    about = play.get("about", {})
    matchup = play.get("matchup", {})
    pitch = event.get("pitchData", {})
    coords = pitch.get("coordinates", {})
    breaks = pitch.get("breaks", {})
    hit = event.get("hitData", {})
    details = event.get("details", {})
    count = event.get("count", {})
    zone = pitch.get("zone")
    return LiveEvent(
        game_pk=game_pk,
        at_bat_index=int(about.get("atBatIndex", 0)),
        event_index=int(event.get("index", 0)),
        event_kind=_kind(event),
        play_id=event.get("playId"),
        is_pitch=bool(event.get("isPitch", False)),
        pitch_type=details.get("type", {}).get("code"),
        start_speed=_num(pitch.get("startSpeed")),
        end_speed=_num(pitch.get("endSpeed")),
        sz_top=_num(pitch.get("strikeZoneTop", coords.get("szTop"))),
        sz_bottom=_num(pitch.get("strikeZoneBottom", coords.get("szBottom"))),
        px=_num(coords.get("pX")),
        pz=_num(coords.get("pZ")),
        x=_num(coords.get("x")),
        y=_num(coords.get("y")),
        zone=int(zone) if isinstance(zone, int) else None,
        spin_rate=_num(breaks.get("spinRate")),
        spin_direction=_num(breaks.get("spinDirection")),
        break_angle=_num(breaks.get("breakAngle")),
        break_length=_num(breaks.get("breakLength")),
        break_y=_num(breaks.get("breakY")),
        plate_time=_num(pitch.get("plateTime")),
        extension=_num(pitch.get("extension")),
        launch_speed=_num(hit.get("launchSpeed")),
        launch_angle=_num(hit.get("launchAngle")),
        total_distance=_num(hit.get("totalDistance")),
        trajectory=hit.get("trajectory"),
        hardness=hit.get("hardness"),
        location=str(hit["location"]) if hit.get("location") is not None else None,
        description=details.get("description", ""),
        call_code=details.get("call", {}).get("code"),
        event=details.get("event"),
        event_type=details.get("eventType"),
        batter_id=int(matchup.get("batter", {}).get("id", 0) or 0),
        pitcher_id=int(matchup.get("pitcher", {}).get("id", 0) or 0),
        inning=int(about.get("inning", 1)),
        is_top_inning=bool(about.get("isTopInning", True)),
        outs=int(count.get("outs", 0)),
        balls=int(count.get("balls", 0)),
        strikes=int(count.get("strikes", 0)),
        timestamp=event.get("startTime"),
        ts_utc=_micros(event.get("startTime")),
        received_utc=received_utc,
        raw_play={k: v for k, v in play.items() if k != "playEvents"},
        raw_event=event,
    )


def _now_micros() -> int:
    return int(time.time() * 1_000_000)


class _State(msgspec.Struct):
    """Persisted watermark (resume point) of one game's stream."""

    at_bat: int = -1
    event: int = -1
    results_through: int = -1
    status: str = ""
    status_seq: int = 0
    timestamp: str | None = None


class GamedayLiveStreamer:
    """Streams live events of any game; implements ``StreamExtractorProtocol`` (``stream_events``)."""

    def __init__(
        self,
        poll_interval: float | None = None,
        http: HttpClient | None = None,
        config: StreamingConfig | None = None,
        quarantine: Quarantine | None = None,
        lake: LakeConfig | None = None,
        use_diff_patch: bool = True,
    ) -> None:
        self.config = config or StreamingConfig()
        self.poll_interval = (
            poll_interval if poll_interval is not None else self.config.poll_interval_seconds
        )
        self.http = http or get_http_client()
        self._quarantine = quarantine
        self.lake = lake
        self.use_diff_patch = use_diff_patch

    # -- resume state -------------------------------------------------------------------------

    def _state_path(self, game_pk: int) -> Path:
        lake = self.lake or LakeConfig()
        return lake.http_cache_root.parent / "stream" / f"{game_pk}.json"

    def _load(self, game_pk: int, resume: bool) -> _State:
        path = self._state_path(game_pk)
        if resume and path.exists():
            return msgspec.json.decode(path.read_bytes(), type=_State)
        return _State()

    def _save(self, game_pk: int, state: _State) -> None:
        path = self._state_path(game_pk)
        path.parent.mkdir(parents=True, exist_ok=True)
        with atomic_write(path) as part:
            part.write_bytes(msgspec.json.encode(state))

    # -- diffing ------------------------------------------------------------------------------

    def _events(self, game_pk: int, doc: dict[str, Any], state: _State) -> Iterator[LiveEvent]:
        """Events beyond the persisted watermark (monotonic ``(atBatIndex, eventIndex)``)."""
        received = _now_micros()
        plays = doc.get("liveData", {}).get("plays", {}).get("allPlays", [])
        for play in plays:
            about = play.get("about", {})
            ab_idx = int(about.get("atBatIndex", 0))
            if ab_idx < state.at_bat:
                continue
            for event in play.get("playEvents", []):
                ev_idx = int(event.get("index", 0))
                if ab_idx == state.at_bat and ev_idx <= state.event:
                    continue
                state.at_bat, state.event = ab_idx, ev_idx
                yield build_event(game_pk, play, event, received)
            if about.get("isComplete") and ab_idx > state.results_through:
                state.results_through = ab_idx
                result = play.get("result", {})
                yield LiveEvent(
                    game_pk=game_pk,
                    at_bat_index=ab_idx,
                    event_index=-1,
                    event_kind="play_result",
                    description=str(result.get("description", "")),
                    event=result.get("event"),
                    event_type=result.get("eventType"),
                    play_result=result.get("event"),
                    batter_id=int(play.get("matchup", {}).get("batter", {}).get("id", 0) or 0),
                    pitcher_id=int(play.get("matchup", {}).get("pitcher", {}).get("id", 0) or 0),
                    inning=int(about.get("inning", 1)),
                    is_top_inning=bool(about.get("isTopInning", True)),
                    outs=int(play.get("count", {}).get("outs", 0)),
                    balls=int(play.get("count", {}).get("balls", 0)),
                    strikes=int(play.get("count", {}).get("strikes", 0)),
                    timestamp=about.get("endTime"),
                    ts_utc=_micros(about.get("endTime")),
                    received_utc=received,
                    raw_play={k: v for k, v in play.items() if k != "playEvents"},
                )
                if int(play.get("count", {}).get("outs", 0)) >= 3:
                    top = bool(about.get("isTopInning", True))
                    yield LiveEvent(
                        game_pk=game_pk,
                        at_bat_index=ab_idx,
                        event_index=-2,
                        event_kind="half_inning_end",
                        description=f"end of the {'top' if top else 'bottom'} of inning {about.get('inning', 1)}",
                        event="half_inning_end",
                        inning=int(about.get("inning", 1)),
                        is_top_inning=top,
                        outs=3,
                        timestamp=about.get("endTime"),
                        ts_utc=_micros(about.get("endTime")),
                        received_utc=received,
                    )

    @staticmethod
    def _status(doc: dict[str, Any]) -> tuple[str, str]:
        status = doc.get("gameData", {}).get("status", {})
        return str(status.get("abstractGameState", "")), str(status.get("detailedState", ""))

    # -- network ------------------------------------------------------------------------------

    def _decode(self, game_pk: int, content: bytes) -> dict[str, Any] | None:
        try:
            data = msgspec.json.decode(content)
        except msgspec.DecodeError as exc:
            (self._quarantine or get_quarantine()).write(
                "mlb_api",
                "live_feed",
                [content],
                f"undecodable live feed payload: {exc}",
                {"game_pk": game_pk},
            )
            return None
        return data if isinstance(data, dict) else None

    async def _full_feed(self, url: str, etag: str | None) -> tuple[bytes | None, str | None]:
        result = await self.http.get(url, etag=etag, allow=(200, 304))
        if result.not_modified:
            return None, etag
        return result.content, result.etag or etag

    async def _patched(self, game_pk: int, url: str, doc: dict[str, Any]) -> dict[str, Any] | None:
        """Bring ``doc`` up to date through ``timestamps`` + ``diffPatch``; ``None`` = need full feed."""
        current = doc.get("metaData", {}).get("timeStamp")
        if current is None:
            return None
        stamps = await self.http.get(f"{url}/timestamps", allow=(200, 404))
        if stamps.status != 200:
            return None
        try:
            listed = json.loads(stamps.content)
        except ValueError:
            return None
        if not isinstance(listed, list) or not listed:
            return None
        newest = str(listed[-1])
        if newest == current:
            return doc
        if current not in listed:
            return None  # the patch window is unknown to the server: resync
        patch = await self.http.get(
            f"{url}/diffPatch",
            params={"startTimecode": current, "endTimecode": newest},
            allow=(200, 400, 404, 500),
        )
        if patch.status != 200:
            return None
        try:
            body = json.loads(patch.content)
            if isinstance(body, dict) and "liveData" in body:
                # for wide windows the server answers with the complete feed instead of a patch
                return cast(dict[str, Any], body)
            updated = apply_patch(copy.deepcopy(doc), patch_ops(body))
        except (PatchError, ValueError) as exc:
            logger.warning("diffPatch for game %s not applicable (%s); full feed", game_pk, exc)
            return None
        if updated.get("metaData", {}).get("timeStamp") != newest:
            logger.warning("diffPatch for game %s did not reach %s; full feed", game_pk, newest)
            return None
        return cast(dict[str, Any], updated)

    # -- public -------------------------------------------------------------------------------

    async def stream_live_events(
        self, game_pk: int, resume: bool = True
    ) -> AsyncIterator[LiveEvent]:
        """Yield every NEW :class:`LiveEvent` of ``game_pk`` until the game ends or goes quiet.

        Network failures are retried by the shared client; after the retries the error propagates
        (the audit record is ``FAILURE``). Malformed payloads are quarantined and polling continues.
        With ``resume`` a stored watermark suppresses everything already emitted in a past stream.
        """
        url = MLB_FEED_URL.format(game_pk=game_pk)
        state = self._load(game_pk, resume)
        doc: dict[str, Any] | None = None
        etag: str | None = None
        last_activity = time.monotonic()
        emitted = 0
        async with default_audit_logger.async_track(
            operation="mlb_stream", source="mlb_api", endpoint=url
        ) as tracker:
            while True:
                sleep_for = self.poll_interval
                fresh: dict[str, Any] | None = None
                if self.use_diff_patch and doc is not None:
                    try:
                        fresh = await self._patched(game_pk, url, doc)
                    except HttpStatusError as exc:
                        logger.warning("diffPatch polling failed (%s); using the full feed", exc)
                if fresh is None:
                    content, etag = await self._full_feed(
                        url, etag if self.config.enable_conditional_etag else None
                    )
                    if content is not None:
                        decoded = self._decode(game_pk, content)
                        stamp = (decoded or {}).get("metaData", {}).get("timeStamp")
                        if decoded is not None and (
                            doc is None
                            or stamp is None
                            or stamp != doc.get("metaData", {}).get("timeStamp")
                        ):
                            fresh = decoded
                if fresh is not None:
                    changed = fresh is not doc
                    doc = fresh
                    if changed:
                        for event in self._events(game_pk, doc, state):
                            emitted += 1
                            tracker.set_records(emitted)
                            last_activity = time.monotonic()
                            yield event
                        abstract, detailed = self._status(doc)
                        label = detailed or abstract
                        if label and label != state.status:
                            state.status = label
                            yield LiveEvent(
                                game_pk=game_pk,
                                at_bat_index=-1,
                                event_index=state.status_seq,
                                event_kind="game_status",
                                event=detailed,
                                event_type=abstract,
                                description=f"game status: {label}",
                                received_utc=_now_micros(),
                            )
                            state.status_seq += 1
                            emitted += 1
                            last_activity = time.monotonic()
                        state.timestamp = doc.get("metaData", {}).get("timeStamp")
                        self._save(game_pk, state)
                        if abstract in TERMINAL_STATES or detailed in TERMINAL_STATES:
                            return
                        if "Delayed" in detailed:
                            sleep_for = max(sleep_for, DELAYED_POLL_SECONDS)
                idle_minutes = (time.monotonic() - last_activity) / 60.0
                if idle_minutes >= self.config.max_inactivity_minutes:
                    logger.warning(
                        "stream for game %s idle %.0f min; stopping", game_pk, idle_minutes
                    )
                    return
                await asyncio.sleep(sleep_for)

    async def stream_events(
        self, game_pk: int, *args: Any, **kwargs: Any
    ) -> AsyncIterator[dict[str, Any]]:
        """``StreamExtractorProtocol``: the same events as plain dicts (see :class:`LiveEvent`)."""
        resume = bool(kwargs.get("resume", True))
        async for event in self.stream_live_events(game_pk, resume=resume):
            yield event.to_dict()
