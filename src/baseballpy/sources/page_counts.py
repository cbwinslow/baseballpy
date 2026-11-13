"""Which keys the raw pages of Kalshi and Polymarket hold, for the count check of ``verify-roundtrip``.

The pages are JSON, so cells cannot be compared; the distinct keys of all the pages of one raw folder are the rows
the table must hold (a record on two pages, or live and archived, is stored once). Each function knows one
shape; ``core/rawpages.py`` does the walking. Measured on the real lake (2026-11-12): the four counts below equal
the stored rows exactly (Kalshi candlesticks 14,903,320; Polymarket outcomes 467,846 and prices 16,043,908).
"""

import json
from collections.abc import Iterator

Page = dict[str, object]


def _records(body: Page, name: str) -> list[dict[str, object]]:
    found = body.get(name)
    return [r for r in found if isinstance(r, dict)] if isinstance(found, list) else []


def kalshi_candlestick_keys(line: Page, body: Page) -> Iterator[tuple[object, object]]:
    """``(ticker, end_period_ts)`` of a candlestick page: one market's series, or a batch of markets."""
    for market in _records(body, "markets"):
        for candle in _records(market, "candlesticks"):
            yield market.get("market_ticker"), candle.get("end_period_ts")
    ticker = body.get("ticker") or line.get("ticker")
    for candle in _records(body, "candlesticks"):
        yield ticker, candle.get("end_period_ts")


def polymarket_price_keys(line: Page, body: Page) -> Iterator[tuple[object, object]]:
    """``(token id, time)`` of a price-history page (the token is the request's ticker)."""
    for point in _records(body, "history"):
        yield line.get("ticker"), point.get("t")


def polymarket_outcome_keys(_line: Page, body: Page) -> Iterator[tuple[object, int]]:
    """``(market id, outcome index)`` of every outcome the markets of an events page list."""
    for event in _records(body, "events"):
        for market in _records(event, "markets"):
            listed = market.get("outcomes")
            try:
                outcomes = json.loads(listed) if isinstance(listed, str) else listed
            except ValueError:
                continue
            if isinstance(outcomes, list):
                for index in range(len(outcomes)):
                    yield market.get("id"), index
