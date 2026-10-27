"""Normalizer for the SABR Lahman Baseball Database."""

import io
import logging

import pyarrow as pa
import pyarrow.csv as pacsv

from baseballpy.core.quarantine import Quarantine, checked_cast
from baseballpy.sources.lahman.schema import KNOWN_SCHEMAS, LahmanTable

logger = logging.getLogger(__name__)

NULL_VALUES = ["", "NA", "null", "None"]


class LahmanNormalizer:
    """Normalizes raw Lahman CSV bytes into strongly-typed PyArrow Tables.

    Known tables are coerced to their canonical schema with checked casts (uncastable
    cells become NULL and are quarantined). Columns the schema does not know about are
    preserved (with a drift warning) instead of being dropped.
    """

    def __init__(self, quarantine: Quarantine | None = None) -> None:
        self._quarantine = quarantine

    def normalize(
        self,
        raw_data: bytes | str,
        table_name: str | LahmanTable = LahmanTable.BATTING,
    ) -> pa.Table:
        """Parse raw CSV bytes/string for a specific Lahman table."""
        name_str = str(table_name)
        raw_bytes = raw_data.encode("utf-8") if isinstance(raw_data, str) else raw_data

        target_schema = KNOWN_SCHEMAS.get(name_str)
        if target_schema is None:
            # Auxiliary table without a strict static schema: Arrow type inference.
            return pacsv.read_csv(
                io.BytesIO(raw_bytes),
                convert_options=pacsv.ConvertOptions(
                    strings_can_be_null=True, null_values=NULL_VALUES
                ),
            )

        # Read known columns as strings so a single bad cell can be quarantined instead of
        # aborting the whole file; unknown columns keep Arrow's inferred types.
        known = {field.name: pa.string() for field in target_schema}
        table = pacsv.read_csv(
            io.BytesIO(raw_bytes),
            convert_options=pacsv.ConvertOptions(
                column_types=known,
                strings_can_be_null=True,
                null_values=NULL_VALUES,
            ),
        )

        columns: list[pa.ChunkedArray] = []
        for field in target_schema:
            if field.name in table.column_names:
                columns.append(
                    checked_cast(
                        table.column(field.name),
                        field.type,
                        quarantine=self._quarantine,
                        source="lahman",
                        dataset=name_str,
                        column=field.name,
                    )
                )
            else:
                columns.append(pa.chunked_array([pa.nulls(len(table), type=field.type)]))

        fields = list(target_schema)
        extras = [name for name in table.column_names if name not in target_schema.names]
        if extras:
            logger.warning(
                "schema drift: Lahman table %s has unknown column(s) %s; preserving them",
                name_str,
                extras,
            )
            for name in extras:
                column = table.column(name)
                columns.append(column)
                fields.append(pa.field(name, column.type))

        return pa.Table.from_arrays(columns, schema=pa.schema(fields))
