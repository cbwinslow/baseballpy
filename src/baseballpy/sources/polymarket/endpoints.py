"""Polymarket public market-data routes, scope and constants, as data (no network, no side effects).

Every number here comes from a probe (``market-sources`` change): the events list has a keyset
route because the offset route stops at about 2,100 rows; price history is cut into windows of at
most 15 days because longer ones are refused with HTTP 400. Nothing here is a guess.
"""

from dataclasses import dataclass

from baseballpy.core.config import POLYMARKET_CLOB_HOST, POLYMARKET_GAMMA_HOST

GAMMA_BASE = f"https://{POLYMARKET_GAMMA_HOST}"
CLOB_BASE = f"https://{POLYMARKET_CLOB_HOST}"

#: the sport whose events are in scope (owner decision M1: all MLB markets); its tag id is read
#: from ``/sports`` at run time, so a changed id needs no code change
SPORT_SLUG = "mlb"


@dataclass(frozen=True)
class PolymarketEndpoint:
    """One public GET route: where it is and how it pages."""

    name: str
    host_base: str
    path: str
    #: key of the answer that holds the records (``""``: the answer is the list)
    records: str
    page_limit: int = 0
    #: name of the parameter that carries the cursor, and of the answer key that returns the next one
    cursor_param: str = ""
    cursor_key: str = ""


SPORTS = PolymarketEndpoint("sports", GAMMA_BASE, "/sports", records="")
EVENTS = PolymarketEndpoint(
    "events",
    GAMMA_BASE,
    "/events/keyset",
    records="events",
    page_limit=100,
    cursor_param="after_cursor",
    cursor_key="next_cursor",
)
PRICES_HISTORY = PolymarketEndpoint(
    "prices_history", CLOB_BASE, "/prices-history", records="history"
)

ENDPOINTS: tuple[PolymarketEndpoint, ...] = (SPORTS, EVENTS, PRICES_HISTORY)

#: datasets filled from the catalog (one job) and from the price route (one job per market open date)
CATALOG_DATASETS = ("events", "markets", "outcomes")
PRICE_DATASETS = ("prices",)

#: price points per hour (``fidelity`` is in minutes): trades could rebuild finer prices, and the
#: finest history for ~470,000 outcome tokens is hundreds of millions of rows
PRICE_FIDELITY_MINUTES = 60
#: the route refuses a window longer than about 15 days (15 days answered, 16 days gave HTTP 400)
MAX_WINDOW_SECONDS = 14 * 86_400
#: a market's price window ends this long after it closed
WINDOW_MARGIN_SECONDS = 3_600

#: dataset -> primary key columns
DATASET_KEYS: dict[str, tuple[str, ...]] = {
    "events": ("id",),
    "markets": ("id",),
    "outcomes": ("market_id", "outcome_index"),
    "prices": ("token_id", "t"),
}

__all__ = [
    "CATALOG_DATASETS",
    "CLOB_BASE",
    "DATASET_KEYS",
    "ENDPOINTS",
    "EVENTS",
    "GAMMA_BASE",
    "MAX_WINDOW_SECONDS",
    "PRICES_HISTORY",
    "PRICE_DATASETS",
    "PRICE_FIDELITY_MINUTES",
    "SPORTS",
    "SPORT_SLUG",
    "WINDOW_MARGIN_SECONDS",
    "PolymarketEndpoint",
]
