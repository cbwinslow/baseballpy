"""Kalshi public market-data endpoints and the MLB scope, as data (no network, no side effects).

One :class:`KalshiEndpoint` row per route; the generic extractor, the schema generator and the docs
iterate this table, so adding a route is adding a row (``market-sources`` change, ADR 70).
"""

from collections.abc import Mapping
from dataclasses import dataclass

from baseballpy.core.config import KALSHI_HOST

KALSHI_BASE = f"https://{KALSHI_HOST}/trade-api/v2"


@dataclass(frozen=True)
class SeriesScope:
    """Which series are in scope: the owner's rule is every MLB market (``market-sources`` M1).

    A series is in scope when its ticker contains one of ``contains`` or is one of ``tickers`` (league
    and World Series markets carry no ``MLB`` in the ticker) and carries none of ``exclude_tags``
    (another sport or esports sharing the letters).
    """

    category: str
    contains: tuple[str, ...]
    tickers: tuple[str, ...]
    exclude_tags: tuple[str, ...]

    def includes(self, series: Mapping[str, object]) -> bool:
        """True when this series record is in scope."""
        ticker = str(series.get("ticker", ""))
        tags = series.get("tags") or []
        if isinstance(tags, list) and any(tag in self.exclude_tags for tag in tags):
            return False
        return ticker in self.tickers or any(part in ticker for part in self.contains)


MLB_SCOPE = SeriesScope(
    category="Sports",
    contains=("MLB",),
    tickers=("KXWSAL", "KXWSNL", "KXTEAMSINWS"),
    exclude_tags=("Esports",),
)


@dataclass(frozen=True)
class KalshiEndpoint:
    """One public GET route: where it is, where its records sit and how it pages.

    ``fan_out`` says what the route is asked per: ``none`` (once), ``series`` (once per in-scope
    series ticker, as ``series_ticker``). ``dataset`` is the registry dataset the records feed;
    several routes may feed one dataset (live and archived markets), merged by the dataset key.
    """

    name: str
    dataset: str
    path: str
    records: str
    page_limit: int
    fan_out: str = "none"
    params: tuple[tuple[str, str], ...] = ()
    #: paged with the ``cursor`` the answer returns (all routes except the series list)
    paged: bool = True


ENDPOINTS: tuple[KalshiEndpoint, ...] = (
    KalshiEndpoint(
        "series",
        "series",
        "/series",
        "series",
        page_limit=0,
        params=(("category", MLB_SCOPE.category),),
        paged=False,
    ),
    KalshiEndpoint("events", "events", "/events", "events", 200, fan_out="series"),
    KalshiEndpoint("markets", "markets", "/markets", "markets", 1000, fan_out="series"),
    KalshiEndpoint(
        "markets_historical",
        "markets",
        "/historical/markets",
        "markets",
        1000,
        fan_out="series",
    ),
)

BY_NAME: dict[str, KalshiEndpoint] = {e.name: e for e in ENDPOINTS}

#: dataset -> primary key columns (the merge key across the routes that feed it)
DATASET_KEYS: dict[str, tuple[str, ...]] = {
    "series": ("ticker",),
    "events": ("event_ticker",),
    "markets": ("ticker",),
}

__all__ = [
    "BY_NAME",
    "DATASET_KEYS",
    "ENDPOINTS",
    "KALSHI_BASE",
    "KALSHI_HOST",
    "MLB_SCOPE",
    "KalshiEndpoint",
    "SeriesScope",
]
