"""Kalshi JSON records onto the strict schemas (typed, quarantined, never dropped)."""

from collections.abc import Sequence
from typing import Any

import pyarrow as pa

from baseballpy.core.quarantine import Quarantine
from baseballpy.core.schema_tools import normalize_records
from baseballpy.sources.kalshi.schema import KALSHI_SCHEMAS


class KalshiNormalizer:
    """Maps records of one Kalshi dataset onto its generated schema.

    Decimal text becomes exact ``decimal`` columns, times ``timestamp``, nested values JSON text;
    an uncastable cell is quarantined and a key the schema does not know goes to ``_extras`` with a
    one-time ``schema_drift`` warning (rerun ``scripts/gen_kalshi_schemas.py`` to type it).
    """

    def __init__(self, quarantine: Quarantine | None = None) -> None:
        self._quarantine = quarantine

    def normalize(self, dataset: str, records: Sequence[dict[str, Any]]) -> pa.Table:
        """Typed table for ``dataset`` (an empty typed table when there are no records)."""
        schema = KALSHI_SCHEMAS[dataset]
        if not records:
            return schema.empty_table()
        return normalize_records(
            records, schema, source="kalshi", dataset=dataset, quarantine=self._quarantine
        )


__all__ = ["KalshiNormalizer"]
