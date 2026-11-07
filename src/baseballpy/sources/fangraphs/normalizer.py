"""FanGraphs CSV files onto the strict schemas (typed, quarantined, never dropped)."""

from collections.abc import Sequence
from typing import Any

import pyarrow as pa

from baseballpy.core.quarantine import Quarantine
from baseballpy.core.schema_tools import normalize_csv, normalize_records
from baseballpy.sources.fangraphs.schema import FANGRAPHS_SCHEMAS


class FangraphsNormalizer:
    """Maps a FanGraphs CSV onto its generated schema by header name.

    A header the schema does not know goes to ``_extras`` with a one-time ``schema_drift`` warning;
    an uncastable cell is quarantined; an empty cell is NULL.
    """

    def __init__(self, quarantine: Quarantine | None = None) -> None:
        self._quarantine = quarantine

    def normalize(self, dataset: str, raw: bytes) -> pa.Table:
        """Typed table of one file."""
        return normalize_csv(
            raw,
            FANGRAPHS_SCHEMAS[dataset],
            source="fangraphs",
            dataset=dataset,
            quarantine=self._quarantine,
        )

    def normalize_records(self, dataset: str, records: Sequence[dict[str, Any]]) -> pa.Table:
        """Typed table of records already shaped to table column names (a download)."""
        schema = FANGRAPHS_SCHEMAS[dataset]
        if not records:
            return schema.empty_table()
        return normalize_records(
            records, schema, source="fangraphs", dataset=dataset, quarantine=self._quarantine
        )


__all__ = ["FangraphsNormalizer"]
