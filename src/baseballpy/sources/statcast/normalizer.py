"""Normalizer for Baseball Savant (Statcast) pitch tracking data."""

import io
import logging
from collections.abc import Iterator
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from baseballpy.sources.statcast.schema import STATCAST_SCHEMA

logger = logging.getLogger(__name__)


class StatcastNormalizer:
    """Normalizes raw Statcast CSV payloads into strongly-typed PyArrow Tables."""

    def __init__(self, schema: pa.Schema | None = None) -> None:
        self._schema = schema or STATCAST_SCHEMA

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

        parse_options = pacsv.ParseOptions(delimiter=",")
        convert_options = pacsv.ConvertOptions(
            strings_can_be_null=True,
            null_values=["", "NA", "null", "None", "<NA>", "NaN"],
        )

        table = pacsv.read_csv(
            io.BytesIO(raw_bytes),
            parse_options=parse_options,
            convert_options=convert_options,
        )

        num_rows = len(table)
        final_columns: list[pa.ChunkedArray] = []
        final_fields: list[pa.Field] = []

        # 1. Coerce all fields in the canonical schema
        for field in self._schema:
            col_name = field.name
            target_type = field.type

            if col_name in table.column_names:
                chunked = table.column(col_name)

                # Special handling for dates
                if target_type == pa.date32():
                    if chunked.type != pa.date32():
                        # Parse strings like '2024-04-05' to date32
                        try:
                            # Try strptime then cast to date32
                            parsed = pc.strptime(
                                chunked.cast(pa.string()), format="%Y-%m-%d", unit="s"
                            )
                            chunked = pc.cast(parsed, pa.date32())
                        except Exception:
                            chunked = pc.cast(chunked, pa.date32(), safe=False)
                # Special handling for dictionary encoding
                elif pa.types.is_dictionary(target_type):
                    str_arr = chunked.cast(pa.string())
                    chunked = pc.dictionary_encode(str_arr).cast(target_type)
                else:
                    try:
                        chunked = pc.cast(chunked, target_type, safe=False)
                    except Exception as err:
                        logger.warning(
                            "Failed to cast Statcast column %s to %s: %s; falling back to nulls",
                            col_name,
                            target_type,
                            err,
                        )
                        chunked = pa.chunked_array([pa.nulls(num_rows, type=target_type)])
            else:
                # Column missing in this payload, fill with nulls of expected type
                chunked = pa.chunked_array([pa.nulls(num_rows, type=target_type)])

            final_columns.append(chunked)
            final_fields.append(field)

        # 2. Schema Drift Resilience & Full Data Preservation (ADR 9 & ADR 15)
        # Capture any new/unexpected columns present in upstream CSV
        canonical_names = set(self._schema.names)
        for col_name in table.column_names:
            if col_name not in canonical_names:
                logger.info("Preserving newly discovered upstream Statcast column: %s", col_name)
                chunked = table.column(col_name)
                final_columns.append(chunked)
                final_fields.append(pa.field(col_name, chunked.type))

        return pa.Table.from_arrays(final_columns, schema=pa.schema(final_fields))

    def normalize_stream(
        self, raw_data_iter: Iterator[bytes | str | dict[str, Any]]
    ) -> pa.RecordBatchReader:
        """Stream multiple CSV parts into a streaming RecordBatchReader."""
        batches: list[pa.RecordBatch] = []
        for part in raw_data_iter:
            table = self.normalize(part)
            batches.extend(table.to_batches())
        return pa.RecordBatchReader.from_batches(self._schema, batches)
