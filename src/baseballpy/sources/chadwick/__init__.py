"""Chadwick Bureau Register module for player identity resolution."""

from baseballpy.sources.chadwick.extractor import ChadwickExtractor
from baseballpy.sources.chadwick.normalizer import ChadwickNormalizer
from baseballpy.sources.chadwick.register import ChadwickRegister, PlayerRecord
from baseballpy.sources.chadwick.schema import CHADWICK_PEOPLE_SCHEMA

__all__ = [
    "CHADWICK_PEOPLE_SCHEMA",
    "ChadwickExtractor",
    "ChadwickNormalizer",
    "ChadwickRegister",
    "PlayerRecord",
]
