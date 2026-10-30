"""One Python entry point for every registered Statcast dataset: ``table("leaderboard_sprint_speed", 2024)``."""

import pyarrow as pa

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import datasets_for
from baseballpy.core.stores import ProcessedStore
from baseballpy.sources import catalog
from baseballpy.sources.statcast.extractor import StatcastExtractor
from baseballpy.sources.statcast.lb_catalog import LEADERBOARDS
from baseballpy.sources.statcast.leaderboards import StatcastLeaderboardExtractor

PITCH_DATASETS = ("pitches", "pitches_minors")


def datasets() -> list[str]:
    """The names of every registered Statcast dataset (what :func:`table` accepts)."""
    catalog.register_all()
    return sorted(spec.name for spec in datasets_for("statcast"))


def table(
    name: str,
    season: int,
    *,
    refresh: bool = False,
    cache_config: LakeConfig | None = None,
) -> pa.Table:
    """Any registered Statcast dataset for one season, fetched and stored first when needed.

    ``pitches`` and ``pitches_minors`` ingest the whole season (a few hundred thousand rows);
    ``leaderboard_*`` datasets fetch the one leaderboard. Unknown names list the valid ones.
    """
    catalog.register_all()
    config = cache_config or LakeConfig()
    if name in PITCH_DATASETS:
        minors = name == "pitches_minors"
        extractor = StatcastExtractor(cache_config=config)
        extractor.ingest_season(season, refresh=refresh, minors=minors)
        spec = extractor.spec_minors if minors else extractor.spec
        return ProcessedStore(config).read(spec, season)
    for defn in LEADERBOARDS:
        if defn.dataset == name and defn.unsupported is None:
            return StatcastLeaderboardExtractor(cache_config=config).get_leaderboard(
                defn.slug, year=season, refresh=refresh
            )
    raise ValueError(f"unknown statcast dataset {name!r}; known: {datasets()}")


__all__ = ["datasets", "table"]
