"""Plain-dict helpers that shape Polymarket JSON before it is typed (no schema needed).

Keys arrive in ``camelCase``; every column is ``snake_case`` like the rest of the lake. An event
carries its markets inside; they are split into the ``events`` and ``markets`` tables, and the two
outcome tokens of a market become ``outcomes`` rows.
"""

import json
from datetime import UTC, datetime
from typing import Any

from baseballpy.core.schema_tools import snake
from baseballpy.sources.polymarket.endpoints import MAX_WINDOW_SECONDS, WINDOW_MARGIN_SECONDS


def snake_keys(record: dict[str, Any]) -> dict[str, Any]:
    """The record with ``snake_case`` keys (two upstream keys must never collapse into one)."""
    out = {snake(key): value for key, value in record.items()}
    if len(out) != len(record):
        raise ValueError(f"keys of {sorted(record)} collide after snake_case")
    return out


def split_event(event: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The event without its markets, and its markets each with an ``event_id``."""
    markets = [{**m, "eventId": event["id"]} for m in event.get("markets") or []]
    return {k: v for k, v in event.items() if k != "markets"}, markets


def outcome_rows(market: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per outcome of a market: its label, its CLOB token and its last known price."""
    labels = _list(market.get("outcomes"))
    tokens = _list(market.get("clobTokenIds"))
    prices = _list(market.get("outcomePrices"))
    return [
        {
            "marketId": market["id"],
            "conditionId": market.get("conditionId"),
            "outcomeIndex": index,
            "outcome": labels[index] if index < len(labels) else None,
            "tokenId": tokens[index] if index < len(tokens) else None,
            "price": prices[index] if index < len(prices) else None,
        }
        for index in range(max(len(labels), len(tokens), len(prices)))
    ]


def _list(value: object) -> list[Any]:
    """Polymarket sends these lists as JSON text inside the JSON (``"[\\"Yes\\", \\"No\\"]"``)."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise ValueError(f"expected a JSON list, got {value[:40]!r}")
        return parsed
    return []


def epoch(value: object) -> int | None:
    """Unix seconds of an ISO text such as ``2024-09-28 14:50:48+00`` or of a datetime."""
    if not value:
        return None
    moment = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    )
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return int(moment.timestamp())


def price_row(token_id: str, point: dict[str, Any]) -> dict[str, Any]:
    """One price point of a token: ``{"t": seconds, "p": price}`` with the time as an ISO UTC text."""
    seconds = int(point["t"])
    return {
        **point,
        "tokenId": token_id,
        "t": datetime.fromtimestamp(seconds, UTC).isoformat().replace("+00:00", "Z"),
    }


def price_window(
    start: object, end: object, closed: bool | None, now: int
) -> tuple[int, int] | None:
    """Seconds from a market's start to a little after it closed (``None`` when it has no start).

    An open market's window ends now; a closed one at its close (or scheduled end) plus a margin.
    """
    first = epoch(start)
    if first is None:
        return None
    last = now if closed is not True else (epoch(end) or now)
    return first, min(max(last, first) + WINDOW_MARGIN_SECONDS, now)


def raw_price_window(market: dict[str, Any], now: int) -> tuple[int, int] | None:
    """:func:`price_window` of a market as the API sends it (``camelCase`` keys)."""
    return price_window(
        market.get("startDate") or market.get("createdAt"),
        market.get("closedTime") or market.get("endDate"),
        market.get("closed"),
        now,
    )


def windows(start: int, end: int) -> list[tuple[int, int]]:
    """``[start, end]`` cut into pieces of at most 14 days (the route refuses longer ones)."""
    out: list[tuple[int, int]] = []
    cursor = start
    while cursor < end:
        stop = min(cursor + MAX_WINDOW_SECONDS, end)
        out.append((cursor, stop))
        cursor = stop
    return out or [(start, end)]


__all__ = [
    "epoch",
    "outcome_rows",
    "price_row",
    "price_window",
    "raw_price_window",
    "snake_keys",
    "split_event",
    "windows",
]
