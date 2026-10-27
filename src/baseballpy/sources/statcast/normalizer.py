"""Normalizer for Baseball Savant (Statcast) pitch tracking data."""

import logging
from collections.abc import Iterator
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from baseballpy.core.quarantine import Quarantine, checked_cast, get_quarantine
from baseballpy.core.schema_tools import EXTRAS, pack_extras, read_csv_strings
from baseballpy.sources.statcast.schema import STATCAST_SCHEMA

logger = logging.getLogger(__name__)


class StatcastNormalizer:
    """Normalizes raw Statcast CSV payloads into strongly-typed PyArrow Tables."""

    def __init__(
        self, schema: pa.Schema | None = None, quarantine: Quarantine | None = None
    ) -> None:
        self._schema = schema or STATCAST_SCHEMA
        self._quarantine = quarantine

    def _to_date32(self, chunked: pa.ChunkedArray, col_name: str) -> pa.ChunkedArray:
        """Parse ``YYYY-MM-DD`` strings to date32; unparseable values are quarantined."""
        if chunked.type == pa.date32():
            return chunked
        as_str = chunked.cast(pa.string())
        parsed = pc.strptime(as_str, format="%Y-%m-%d", unit="s", error_is_null=True)
        failed = pc.and_(pc.is_valid(as_str), pc.is_null(parsed))
        if pc.any(failed).as_py():
            bad = pc.filter(as_str, failed).to_pylist()
            (self._quarantine or get_quarantine()).write(
                "statcast",
                "pitches",
                [{"column": col_name, "value": v} for v in bad],
                f"unparseable dates in column {col_name!r}",
            )
        return pc.cast(parsed, pa.date32())

    @property
    def schema(self) -> pa.Schema:
        """Return canonical Statcast schema."""
        return self._schema

    def normalize(self, raw_data: bytes | str | dict[str, Any] | list[Any]) -> pa.Table:
        """Parse raw CSV bytes into a strongly-typed PyArrow Table matching the canonical schema."""
        if isinstance(raw_data, str):
            raw_bytes = raw_data.encode("utf-8")
        elif isinstance(raw_data, bytes):
            raw_bytes = raw_data
        else:
            raise TypeError(f"Expected bytes or str for Statcast CSV, got {type(raw_data)}")

        if not raw_bytes.strip():
            # Return empty table with schema
            return pa.Table.from_batches([], schema=self._schema)

        table = read_csv_strings(raw_bytes)
        num_rows = table.num_rows
        by_name = dict.fromkeys(table.column_names)
        final_columns: list[pa.ChunkedArray | pa.Array] = []
        for field in self._schema:
            col_name = field.name
            target_type = field.type
            if col_name == EXTRAS:
                continue
            if col_name not in by_name:
                final_columns.append(pa.nulls(num_rows, type=target_type))
                continue
            chunked = table.column(col_name)
            if target_type == pa.date32():
                final_columns.append(self._to_date32(chunked, col_name))
            elif pa.types.is_dictionary(target_type):
                final_columns.append(pc.dictionary_encode(chunked).cast(target_type))
            else:
                final_columns.append(
                    checked_cast(
                        chunked,
                        target_type,
                        quarantine=self._quarantine,
                        source="statcast",
                        dataset="pitches",
                        column=col_name,
                    )
                )
        known = {f.name for f in self._schema}
        extra_names = [n for n in table.column_names if n not in known]
        fields = [f for f in self._schema if f.name != EXTRAS]
        if EXTRAS in known:
            # unknown upstream columns are kept as JSON (never dropped, never a per-part schema)
            final_columns.append(
                pack_extras(table, extra_names, source="statcast", dataset="pitches")
            )
            fields.append(self._schema.field(EXTRAS))
        elif extra_names:
            logger.warning("dropping unknown Statcast columns for a custom schema: %s", extra_names)
        return pa.Table.from_arrays(
            [c if isinstance(c, pa.ChunkedArray) else pa.chunked_array([c]) for c in final_columns],
            schema=pa.schema(fields),
        )

    def normalize_stream(
        self, raw_data_iter: Iterator[bytes | str | dict[str, Any]]
    ) -> pa.RecordBatchReader:
        """Stream multiple CSV parts into a streaming RecordBatchReader."""
        batches: list[pa.RecordBatch] = []
        for part in raw_data_iter:
            table = self.normalize(part)
            batches.extend(table.to_batches())
        return pa.RecordBatchReader.from_batches(self._schema, batches)
