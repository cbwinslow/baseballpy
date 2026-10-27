"""Registration of built-in source ingest adapters."""

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


def register_all_adapters() -> None:
    """Register ingest adapter factories for all five built-in sources."""
    register_adapter("statcast", _statcast_factory)
    register_adapter("mlb_api", _mlb_api_factory)
    register_adapter("lahman", _lahman_factory)
    register_adapter("chadwick", _chadwick_factory)
    register_adapter("retrosheet", _retrosheet_factory)


__all__ = ["register_all_adapters"]
