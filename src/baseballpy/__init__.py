"""baseballpy: Fast, modular, and strongly-typed baseball data ingestion layer.

Unified extraction, normalization, and ingestion for Statcast, MLB API, Lahman,
Chadwick Registers, and Retrosheet into DuckDB, Polars, PyArrow, and dlt.
"""

from baseballpy.core.protocols import (
    ExtractorProtocol,
    LiveEventConsumerProtocol,
    NormalizerProtocol,
    SinkProtocol,
    StreamExtractorProtocol,
)
from baseballpy.sources.chadwick.register import ChadwickRegister, PlayerRecord

__version__ = "0.1.0"


def resolve_player(
    *,
    mlbam: int | None = None,
    retro: str | None = None,
    bbref: str | None = None,
    fangraphs: int | None = None,
    person: str | None = None,
    name: str | None = None,
) -> PlayerRecord | list[PlayerRecord] | None:
    """Resolve a player across identifier systems (MLBAM, Retrosheet, BBRef, FanGraphs)."""
    reg = ChadwickRegister.load()
    if name is not None:
        return reg.search_name(name)
    return reg.resolve(
        mlbam=mlbam,
        retro=retro,
        bbref=bbref,
        fangraphs=fangraphs,
        person=person,
    )


__all__ = [
    "ChadwickRegister",
    "ExtractorProtocol",
    "LiveEventConsumerProtocol",
    "NormalizerProtocol",
    "PlayerRecord",
    "SinkProtocol",
    "StreamExtractorProtocol",
    "__version__",
    "resolve_player",
]
