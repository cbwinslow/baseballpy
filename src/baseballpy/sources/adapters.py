"""Registration of built-in source ingest adapters."""

from baseballpy.core.units import register_normalizer, register_unit_resolver
from baseballpy.ingest.adapters import IngestAdapter, register_adapter


def _statcast_factory() -> IngestAdapter:
    from baseballpy.sources.statcast.adapter import StatcastAdapter

    return StatcastAdapter()


def _mlb_api_factory() -> IngestAdapter:
    from baseballpy.sources.mlb_api.adapter import MlbApiAdapter

    return MlbApiAdapter()


def _lahman_factory() -> IngestAdapter:
    from baseballpy.sources.lahman.adapter import LahmanAdapter

    return LahmanAdapter()


def _chadwick_factory() -> IngestAdapter:
    from baseballpy.sources.chadwick.adapter import ChadwickAdapter

    return ChadwickAdapter()


def _retrosheet_factory() -> IngestAdapter:
    from baseballpy.sources.retrosheet.adapter import RetrosheetAdapter

    return RetrosheetAdapter()


def _kalshi_factory() -> IngestAdapter:
    from baseballpy.sources.kalshi.adapter import KalshiAdapter

    return KalshiAdapter()


def _polymarket_factory() -> IngestAdapter:
    from baseballpy.sources.polymarket.adapter import PolymarketAdapter

    return PolymarketAdapter()


def _bref_factory() -> IngestAdapter:
    from baseballpy.sources.bref.adapter import BrefAdapter

    return BrefAdapter()


def _fangraphs_factory() -> IngestAdapter:
    from baseballpy.sources.fangraphs.adapter import FangraphsAdapter

    return FangraphsAdapter()


def register_all_adapters() -> None:
    """Register ingest adapter factories for all built-in sources."""
    register_adapter("statcast", _statcast_factory)
    register_adapter("mlb_api", _mlb_api_factory)
    register_adapter("lahman", _lahman_factory)
    register_adapter("chadwick", _chadwick_factory)
    register_adapter("retrosheet", _retrosheet_factory)
    register_adapter("kalshi", _kalshi_factory)
    register_adapter("polymarket", _polymarket_factory)
    register_adapter("bref", _bref_factory)
    register_adapter("fangraphs", _fangraphs_factory)
    from baseballpy.core.roundtrip import register_raw_reader
    from baseballpy.sources.statcast.roundtrip import raw_reader as statcast_raw_reader

    register_raw_reader("statcast", statcast_raw_reader)  # leaderboard pages decode to rows
    from baseballpy.sources.retrosheet.roundtrip import raw_reader as retrosheet_raw_reader

    register_raw_reader("retrosheet", retrosheet_raw_reader)  # zips, headerless logs and rosters
    from baseballpy.core.roundtrip import register_count_check
    from baseballpy.sources.retrosheet.linecounts import RULES, counter

    for dataset in RULES:  # event files are not CSV: their rows are counted against the raw lines
        register_count_check("retrosheet", dataset, counter(dataset))
    from baseballpy.core.rawpages import pages_counter, tuples_counter
    from baseballpy.sources import page_counts

    # Kalshi and Polymarket keep JSON pages: the distinct ids in the raw pages are the rows the tables must hold
    # (kalshi series is left out on purpose: the raw pages list every series, the table keeps the MLB ones;
    # trades, candlesticks, prices and outcomes were measured equal to the stored rows on 2026-11-12)
    register_count_check(
        "kalshi", "events", pages_counter("kalshi", "events", "events", "event_ticker")
    )
    register_count_check(
        "kalshi", "markets", pages_counter("kalshi", "markets", "markets", "ticker")
    )
    register_count_check(
        "polymarket", "events", pages_counter("polymarket", "events", "events", "id")
    )
    register_count_check(
        "polymarket", "markets", pages_counter("polymarket", "events", "events", "id", ("markets",))
    )
    register_count_check(
        "kalshi", "trades", pages_counter("kalshi", "trades", "trades", "trade_id")
    )
    register_count_check(
        "kalshi",
        "candlesticks",
        tuples_counter("kalshi", "candlesticks", page_counts.kalshi_candlestick_keys),
    )
    register_count_check(
        "polymarket",
        "prices",
        tuples_counter("polymarket", "prices", page_counts.polymarket_price_keys),
    )
    register_count_check(
        "polymarket",
        "outcomes",
        tuples_counter("polymarket", "events", page_counts.polymarket_outcome_keys),
    )
    from baseballpy.sources.mlb_api.game_segments import (
        game_dataset_names,
        game_normalizer,
        game_unit,
    )

    register_unit_resolver("mlb_api", game_unit)  # raw answers are grouped by game
    register_normalizer(
        "mlb_api", game_normalizer, game_dataset_names
    )  # and cut into datasets by this function


__all__ = ["register_all_adapters"]
