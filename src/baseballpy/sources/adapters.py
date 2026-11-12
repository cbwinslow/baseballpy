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
