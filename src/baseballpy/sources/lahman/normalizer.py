"""Normalizer for the SABR Lahman Baseball Database."""

import io
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from baseballpy.sources.lahman.schema import KNOWN_SCHEMAS, LahmanTable


class LahmanNormalizer:
    """Normalizes raw Lahman CSV bytes into strongly-typed PyArrow Tables."""

    def normalize(
        self,
        raw_data: bytes | str,
        table_name: str | LahmanTable = LahmanTable.BATTING,
    ) -> pa.Table:
        """Parse raw CSV bytes/string for a specific Lahman table."""
        name_str = str(table_name)
        raw_bytes = raw_data.encode("utf-8") if isinstance(raw_data, str) else raw_data

        target_schema = KNOWN_SCHEMAS.get(name_str)
        if target_schema:
            column_types: dict[str, Any] = {}
            for field in target_schema:
                # Dates are read as string first then cast to date32
                if pa.types.is_date(field.type):
                    column_types[field.name] = pa.string()
                else:
                    column_types[field.name] = field.type

            convert_options = pacsv.ConvertOptions(
                column_types=column_types,
                strings_can_be_null=True,
                null_values=["", "NA", "null", "None"],
            )
            table = pacsv.read_csv(
                io.BytesIO(raw_bytes),
                convert_options=convert_options,
            )

            # Cast date columns and reorder according to canonical schema
            selected_columns: list[pa.ChunkedArray] = []
            for field in target_schema:
                if field.name in table.column_names:
                    col = table.column(field.name)
                    if pa.types.is_date(field.type):
                        casted = pc.cast(col, pa.date32())
                        selected_columns.append(casted)
                    else:
                        selected_columns.append(col.cast(field.type))
                else:
                    selected_columns.append(
                        pa.chunked_array([pa.nulls(len(table), type=field.type)])
                    )

            return pa.Table.from_arrays(selected_columns, schema=target_schema)

        # Fallback for auxiliary tables without strict static schema
        convert_options = pacsv.ConvertOptions(
            strings_can_be_null=True,
            null_values=["", "NA", "null", "None"],
        )
        return pacsv.read_csv(io.BytesIO(raw_bytes), convert_options=convert_options)
