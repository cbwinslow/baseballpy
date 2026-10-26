"""Normalizer for sharded Chadwick Bureau Player Register and nickname tables."""

import io
from collections.abc import Iterator
from typing import Any

import pyarrow as pa
import pyarrow.csv as pacsv

from baseballpy.sources.chadwick.schema import (
    CHADWICK_NAMES_SCHEMA,
    CHADWICK_PEOPLE_SCHEMA,
)


class ChadwickNormalizer:
    """Normalizes raw Chadwick CSV bytes (single or sharded) into strongly-typed PyArrow Tables."""

    @property
    def schema(self) -> pa.Schema:
        """Return canonical Chadwick people PyArrow schema."""
        return CHADWICK_PEOPLE_SCHEMA

    def normalize(self, raw_data: bytes | str | dict[str, Any] | list[Any]) -> pa.Table:
        """Parse raw CSV input (single bytes/str, list of bytes, or dict of shard bytes)."""
        if isinstance(raw_data, (bytes, str)):
            return self._normalize_single_csv(raw_data)

        if isinstance(raw_data, dict):
            # Dict of shard files, e.g. {"people-0.csv": b"...", "people-1.csv": b"..."}
            shard_tables: list[pa.Table] = []
            for name, content in raw_data.items():
                if name.startswith("people-") and isinstance(content, (bytes, str)):
                    shard_tables.append(self._normalize_single_csv(content))
            if not shard_tables:
                return pa.Table.from_batches([], schema=self.schema)
            return pa.concat_tables(shard_tables)

        if isinstance(raw_data, list):
            tables = [
                self._normalize_single_csv(item)
                for item in raw_data
                if isinstance(item, (bytes, str))
            ]
            if not tables:
                return pa.Table.from_batches([], schema=self.schema)
            return pa.concat_tables(tables)

        raise TypeError(f"Unsupported data type for Chadwick normalizer: {type(raw_data)}")

    def normalize_names(self, raw_data: bytes | str) -> pa.Table:
        """Parse names.csv (alternate spellings, nicknames, birth names)."""
        raw_bytes = raw_data.encode("utf-8") if isinstance(raw_data, str) else raw_data
        convert_opts = pacsv.ConvertOptions(
            column_types={f.name: f.type for f in CHADWICK_NAMES_SCHEMA},
            strings_can_be_null=True,
            null_values=["", "NA", "null", "None"],
        )
        table = pacsv.read_csv(
            io.BytesIO(raw_bytes),
            convert_options=convert_opts,
        )
        selected = []
        for field in CHADWICK_NAMES_SCHEMA:
            if field.name in table.column_names:
                selected.append(table.column(field.name).cast(field.type))
            else:
                selected.append(pa.nulls(len(table), type=field.type))
        return pa.Table.from_arrays(selected, schema=CHADWICK_NAMES_SCHEMA)

    def _normalize_single_csv(self, raw_data: bytes | str) -> pa.Table:
        """Parse a single Chadwick CSV into an Arrow Table."""
        raw_bytes = raw_data.encode("utf-8") if isinstance(raw_data, str) else raw_data

        convert_options = pacsv.ConvertOptions(
            column_types={
                "key_person": pa.string(),
                "key_uuid": pa.string(),
                "key_mlbam": pa.int32(),
                "key_retro": pa.string(),
                "key_bbref": pa.string(),
                "key_bbref_minors": pa.string(),
                "key_fangraphs": pa.int32(),
                "key_npb": pa.string(),
                "key_wikidata": pa.string(),
                "name_last": pa.string(),
                "name_first": pa.string(),
                "name_given": pa.string(),
                "name_suffix": pa.string(),
                "name_matrilineal": pa.string(),
                "name_nick": pa.string(),
                "birth_year": pa.int16(),
                "birth_month": pa.int8(),
                "birth_day": pa.int8(),
                "death_year": pa.int16(),
                "death_month": pa.int8(),
                "death_day": pa.int8(),
                "pro_played_first": pa.int16(),
                "pro_played_last": pa.int16(),
                "mlb_played_first": pa.int16(),
                "mlb_played_last": pa.int16(),
                "col_played_first": pa.int16(),
                "col_played_last": pa.int16(),
            },
            strings_can_be_null=True,
            null_values=["", "NA", "null", "None"],
        )

        table = pacsv.read_csv(
            io.BytesIO(raw_bytes),
            convert_options=convert_options,
        )

        # Align to canonical schema
        selected_columns = []
        for field in self.schema:
            if field.name in table.column_names:
                selected_columns.append(table.column(field.name).cast(field.type))
            else:
                selected_columns.append(pa.nulls(len(table), type=field.type))

        return pa.Table.from_arrays(selected_columns, schema=self.schema)

    def normalize_stream(
        self, raw_data_iter: Iterator[bytes | str | dict[str, Any]]
    ) -> pa.RecordBatchReader:
        """Convert a stream of raw CSV segments into a streaming RecordBatchReader."""
        chunks: list[bytes] = []
        for item in raw_data_iter:
            if isinstance(item, str):
                chunks.append(item.encode("utf-8"))
            elif isinstance(item, bytes):
                chunks.append(item)
        full_table = self.normalize(b"".join(chunks))
        return full_table.to_reader()
