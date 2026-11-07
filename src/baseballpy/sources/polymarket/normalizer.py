"""Polymarket JSON records onto the strict schemas (typed, quarantined, never dropped)."""

from collections.abc import Sequence
from typing import Any

import pyarrow as pa

from baseballpy.core.quarantine import Quarantine
from baseballpy.core.schema_tools import normalize_records
from baseballpy.sources.polymarket.records import outcome_rows, snake_keys, split_event
from baseballpy.sources.polymarket.schema import POLYMARKET_SCHEMAS


class PolymarketNormalizer:
    """Maps records of one Polymarket dataset onto its generated schema."""

    def __init__(self, quarantine: Quarantine | None = None) -> None:
        self._quarantine = quarantine

    def normalize(self, dataset: str, records: Sequence[dict[str, Any]]) -> pa.Table:
        """Typed table for ``dataset`` (an empty typed table when there are no records)."""
        schema = POLYMARKET_SCHEMAS[dataset]
        if not records:
            return schema.empty_table()
        return normalize_records(
            [snake_keys(r) for r in records],
            schema,
            source="polymarket",
            dataset=dataset,
            quarantine=self._quarantine,
        )


__all__ = ["PolymarketNormalizer", "outcome_rows", "snake_keys", "split_event"]
