"""Normalizer for Chadwick Bureau Player Register."""

import io
from collections.abc import Iterator
from typing import Any

import pyarrow as pa
import pyarrow.csv as pacsv

from baseballpy.sources.chadwick.schema import CHADWICK_PEOPLE_SCHEMA


class ChadwickNormalizer:
    """Normalizes raw Chadwick CSV bytes into a strongly-typed PyArrow Table."""

    @property
    def schema(self) -> pa.Schema:
        """Return the canonical Chadwick PyArrow schema."""
        return CHADWICK_PEOPLE_SCHEMA

    def normalize(self, raw_data: bytes | str | dict[str, Any] | list[Any]) -> pa.Table:
        """Parse CSV bytes/string into a strongly-typed PyArrow Table matching the schema."""
        if isinstance(raw_data, str):
            raw_bytes = raw_data.encode("utf-8")
        elif isinstance(raw_data, bytes):
            raw_bytes = raw_data
        else:
            raise TypeError(f"Expected bytes or str for Chadwick CSV, got {type(raw_data)}")

        parse_options = pacsv.ParseOptions(delimiter=",")
        # Define nullable types for conversion
        convert_options = pacsv.ConvertOptions(
            column_types={
                "key_person": pa.string(),
                "key_uuid": pa.string(),
                "key_mlbam": pa.int32(),
                "key_retro": pa.string(),
                "key_bbref": pa.string(),
                "key_fangraphs": pa.int32(),
                "name_last": pa.string(),
                "name_first": pa.string(),
                "name_given": pa.string(),
                "birth_year": pa.int16(),
                "birth_month": pa.int8(),
                "birth_day": pa.int8(),
                "mlb_played_first": pa.int16(),
                "mlb_played_last": pa.int16(),
            },
            strings_can_be_null=True,
            null_values=["", "NA", "null", "None"],
        )

        table = pacsv.read_csv(
            io.BytesIO(raw_bytes),
            parse_options=parse_options,
            convert_options=convert_options,
        )

        # Select and order only the columns defined in our canonical schema
        selected_columns = []
        for field in self.schema:
            if field.name in table.column_names:
                selected_columns.append(table.column(field.name).cast(field.type))
            else:
                # Fill missing column with null array of correct type
                selected_columns.append(pa.nulls(len(table), type=field.type))

        return pa.Table.from_arrays(selected_columns, schema=self.schema)

    def normalize_stream(
        self, raw_data_iter: Iterator[bytes | str | dict[str, Any]]
    ) -> pa.RecordBatchReader:
        """Convert a stream of raw CSV segments into a streaming RecordBatchReader."""
        # For Chadwick bulk register, whole table is read
        chunks: list[bytes] = []
        for item in raw_data_iter:
            if isinstance(item, str):
                chunks.append(item.encode("utf-8"))
            elif isinstance(item, bytes):
                chunks.append(item)
        full_table = self.normalize(b"".join(chunks))
        return full_table.to_reader()
