"""Chadwick Bureau Player Register source package."""

from typing import Any

from baseballpy.sources.chadwick.extractor import ChadwickExtractor
from baseballpy.sources.chadwick.normalizer import ChadwickNormalizer
from baseballpy.sources.chadwick.register import ChadwickRegister, PlayerRecord
from baseballpy.sources.chadwick.schema import (
    CHADWICK_COUNTRIES_SCHEMA,
    CHADWICK_LINKS_SCHEMA,
    CHADWICK_NAMES_SCHEMA,
    CHADWICK_PEOPLE_SCHEMA,
    PlayerIdType,
)


def get_register(refresh: bool = False) -> ChadwickRegister:
    """Return the global Chadwick player register index."""
    return ChadwickRegister.load(refresh=refresh)


def crosswalk(
    id_value: Any,
    from_type: PlayerIdType | str,
    to_type: PlayerIdType | str,
) -> Any | None:
    """Convenience helper to crosswalk between player identifier systems."""
    reg = get_register()
    return reg.resolve_id(id_value, from_type=from_type, to_type=to_type)


__all__ = [
    "CHADWICK_COUNTRIES_SCHEMA",
    "CHADWICK_LINKS_SCHEMA",
    "CHADWICK_NAMES_SCHEMA",
    "CHADWICK_PEOPLE_SCHEMA",
    "ChadwickExtractor",
    "ChadwickNormalizer",
    "ChadwickRegister",
    "PlayerIdType",
    "PlayerRecord",
    "crosswalk",
    "get_register",
]
