"""One Python entry point for every registered MLB Stats API dataset: ``table("teams")``, ``table("standings", 2025)``."""

from typing import Any

import pyarrow as pa

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import datasets_for
from baseballpy.sources import catalog
from baseballpy.sources.mlb_api.api import MlbApiSource
from baseballpy.sources.mlb_api.endpoints import BY_NAME

#: datasets with their own hand-written extractor (the rest are declarative endpoints): the
#: ``MlbApiSource`` method that returns them and the table to pick from a (batting, pitching) pair
HAND_WRITTEN: dict[str, tuple[str, int | None]] = {
    "teams": ("teams", None),
    "venues": ("venues", None),
    "standings": ("standings", None),
    "transactions": ("transactions", None),
    "draft": ("draft", None),
    "schedule": ("schedule", None),
    "rosters": ("roster", None),
    "box_batting": ("boxscore", 0),
    "box_pitching": ("boxscore", 1),
}


def datasets() -> list[str]:
    """The names of every registered MLB dataset (what :func:`table` accepts)."""
    catalog.register_all()
    return sorted(spec.name for spec in datasets_for("mlb_api"))


def table(
    name: str,
    season: int | None = None,
    *,
    refresh: bool = False,
    cache_config: LakeConfig | None = None,
    **arguments: Any,
) -> pa.Table:
    """Any registered MLB dataset by its registry name, fetched and stored first when needed.

    ``arguments`` are the extra inputs a dataset needs: ``team_id`` for ``rosters``, ``game_pk``
    for ``box_batting``/``box_pitching``, ``person_ids``, ``game_pks``, ``updated_since`` or
    ``query`` for the declarative endpoints. Unknown names list the valid ones.
    """
    catalog.register_all()
    source = MlbApiSource(cache_config=cache_config)
    if name in HAND_WRITTEN:
        method, pick = HAND_WRITTEN[name]
        if name in ("standings", "transactions", "draft"):
            arguments.setdefault("year" if name == "draft" else "season", season)
        elif name == "schedule":
            arguments.setdefault("season", season)
        result = getattr(source, method)(refresh=refresh, **arguments)
        return result if pick is None else result[pick]
    if name in BY_NAME and name in datasets():
        return source.endpoint(name, season=season, refresh=refresh, **arguments)
    raise ValueError(f"unknown mlb_api dataset {name!r}; known: {datasets()}")


__all__ = ["datasets", "table"]
