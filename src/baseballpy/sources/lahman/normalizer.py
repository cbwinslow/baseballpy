"""Normalizer for the SABR Lahman Baseball Database."""

import logging

import pyarrow as pa

from baseballpy.core.quarantine import Quarantine
from baseballpy.core.schema_tools import normalize_csv, read_csv_strings
from baseballpy.sources.lahman.schema import KNOWN_SCHEMAS, LahmanTable

logger = logging.getLogger(__name__)


class LahmanNormalizer:
    """Normalizes raw Lahman CSV bytes into strongly-typed PyArrow Tables.

    Tables are matched to their generated strict schema by *header name* (column order and BOMs
    do not matter). Cells that cannot be cast are quarantined (never silently NULLed) and columns
    the schema does not know are preserved as JSON in ``_extras`` with a one-time drift warning.
    A table that is not one of the 27 known ones keeps all columns as strings (nothing dropped).
    """

    def __init__(self, quarantine: Quarantine | None = None) -> None:
        self._quarantine = quarantine

    def normalize(
        self,
        raw_data: bytes | str,
        table_name: str | LahmanTable = LahmanTable.BATTING,
    ) -> pa.Table:
        """Parse raw CSV bytes/string for a specific Lahman table."""
        name = str(table_name)
        schema = KNOWN_SCHEMAS.get(name)
        if schema is None:
            logger.warning(
                "Lahman table %s has no strict schema yet; storing all columns as strings", name
            )
            return read_csv_strings(raw_data)
        return normalize_csv(
            raw_data, schema, source="lahman", dataset=name, quarantine=self._quarantine
        )
