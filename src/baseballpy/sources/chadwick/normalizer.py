"""Normalizer for the sharded Chadwick Bureau Player Register and its auxiliary tables."""

from collections.abc import Iterator
from typing import Any

import pyarrow as pa

from baseballpy.core.quarantine import Quarantine
from baseballpy.core.schema_tools import normalize_csv
from baseballpy.sources.chadwick.schema import CHADWICK_SCHEMAS


class ChadwickNormalizer:
    """Maps raw Chadwick CSV bytes onto the generated strict schemas by header name.

    Unknown columns are preserved as JSON in ``_extras`` (never dropped) and uncastable cells are
    quarantined rather than silently NULLed.
    """

    def __init__(self, quarantine: Quarantine | None = None) -> None:
        self._quarantine = quarantine

    @property
    def schema(self) -> pa.Schema:
        """The canonical ``register`` (people) schema."""
        return CHADWICK_SCHEMAS["register"]

    def _csv(self, raw: bytes | str, dataset: str) -> pa.Table:
        return normalize_csv(
            raw,
            CHADWICK_SCHEMAS[dataset],
            source="chadwick",
            dataset=dataset,
            quarantine=self._quarantine,
        )

    def normalize(self, raw_data: bytes | str | dict[str, Any] | list[Any]) -> pa.Table:
        """Parse people shards: one CSV, a list of CSVs, or ``{"people-0.csv": bytes, ...}``."""
        if isinstance(raw_data, bytes | str):
            return self._csv(raw_data, "register")
        if isinstance(raw_data, dict):
            tables = [
                self._csv(content, "register")
                for name, content in sorted(raw_data.items())
                if name.startswith("people-") and isinstance(content, bytes | str)
            ]
        elif isinstance(raw_data, list):
            tables = [
                self._csv(item, "register") for item in raw_data if isinstance(item, bytes | str)
            ]
        else:
            raise TypeError(f"Unsupported data type for Chadwick normalizer: {type(raw_data)}")
        if not tables:
            return self.schema.empty_table()
        return pa.concat_tables(tables)

    def normalize_names(self, raw_data: bytes | str) -> pa.Table:
        """Parse ``names.csv`` (alternate spellings, nicknames, birth names)."""
        return self._csv(raw_data, "register_names")

    def normalize_links(self, raw_data: bytes | str) -> pa.Table:
        """Parse ``links.csv`` (external identifiers: ``key_person, source, value``)."""
        return self._csv(raw_data, "register_links")

    def normalize_countries(self, raw_data: bytes | str) -> pa.Table:
        """Parse ``countries.csv`` (ISO / IOC / FIFA codes)."""
        return self._csv(raw_data, "register_countries")

    def normalize_stream(
        self, raw_data_iter: Iterator[bytes | str | dict[str, Any]]
    ) -> pa.RecordBatchReader:
        """Convert a stream of raw CSV segments into a streaming RecordBatchReader."""
        tables: list[pa.Table] = []
        for item in raw_data_iter:
            if isinstance(item, bytes | str):
                tables.append(self._csv(item, "register"))
            else:
                tables.append(self.normalize(item))
        full = pa.concat_tables(tables) if tables else self.schema.empty_table()
        return full.to_reader()
