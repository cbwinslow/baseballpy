"""Baseball-Reference WAR files onto the strict schemas (typed, quarantined, never dropped)."""

import pyarrow as pa

from baseballpy.core.quarantine import Quarantine
from baseballpy.core.schema_tools import normalize_csv
from baseballpy.sources.bref.endpoints import NULL_TOKEN
from baseballpy.sources.bref.schema import BREF_SCHEMAS


class BrefNormalizer:
    """Maps a WAR file (CSV text with ``NULL`` for missing) onto its generated schema.

    A header the schema does not know goes to ``_extras``; an uncastable cell is quarantined.
    """

    def __init__(self, quarantine: Quarantine | None = None) -> None:
        self._quarantine = quarantine

    def normalize(self, dataset: str, raw: bytes) -> pa.Table:
        """Typed table of one WAR file."""
        return normalize_csv(
            raw,
            BREF_SCHEMAS[dataset],
            source="bref",
            dataset=dataset,
            quarantine=self._quarantine,
            null_values=("", NULL_TOKEN),
        )


__all__ = ["BrefNormalizer"]
