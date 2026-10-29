"""CSV sink: pyarrow writes the file, a ``<name>.schema.json`` sidecar keeps the Arrow types.

CSV cannot carry types, so the sidecar lists every column (name, Arrow type, nullability) and holds
the exact Arrow schema; :func:`read_csv_typed` uses it to read the file back unchanged. An empty cell
is NULL (the rule the importers use too); nested columns cannot be written and are refused.
"""

import base64
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.csv as pacsv

from baseballpy.core.atomic import atomic_write
from baseballpy.core.audit import default_audit_logger

SCHEMA_FORMAT = "baseballpy-csv-schema/1"


def sidecar_path(csv_path: Path | str) -> Path:
    """``register.csv`` -> ``register.schema.json`` in the same folder."""
    return Path(csv_path).with_suffix(".schema.json")


def _check_writable(schema: pa.Schema) -> None:
    if nested := [f.name for f in schema if pa.types.is_nested(f.type)]:
        raise ValueError(
            f"CSV cannot hold nested column(s) {nested}; export this dataset to parquet instead"
        )


def _flat_schema(schema: pa.Schema) -> pa.Schema:
    """The schema as pyarrow writes it (dictionary columns become their value type)."""
    return pa.schema(
        [
            pa.field(f.name, f.type.value_type if pa.types.is_dictionary(f.type) else f.type)
            for f in schema
        ]
    )


def _sidecar_text(schema: pa.Schema) -> str:
    ipc = base64.b64encode(schema.serialize().to_pybytes()).decode("ascii")
    info: dict[str, Any] = {
        "format": SCHEMA_FORMAT,
        "columns": [{"name": f.name, "type": str(f.type), "nullable": f.nullable} for f in schema],
        "arrow_ipc_schema_base64": ipc,
    }
    return json.dumps(info, indent=2) + "\n"


def _write_sidecar(csv_path: Path, schema: pa.Schema) -> None:
    with atomic_write(sidecar_path(csv_path), mode="w") as part:
        part.write_text(_sidecar_text(schema), encoding="utf-8")


class CsvSink:
    """Writes Arrow tables to UTF-8 CSV with a header, atomically, plus the schema sidecar."""

    def write(self, table: pa.Table, destination: str, **kwargs: Any) -> int:
        """Write ``table`` to the file ``destination``; returns the rows written."""
        _check_writable(table.schema)
        path = Path(destination)
        flat = table.cast(_flat_schema(table.schema))
        with default_audit_logger.track(
            operation="csv_write", source="sink", destination=str(path)
        ) as tracker:
            with atomic_write(path) as part:
                pacsv.write_csv(flat, part)
            _write_sidecar(path, table.schema)
            rows = len(table)
            tracker.set_records(rows)
        return rows

    def write_stream(self, reader: pa.RecordBatchReader, destination: str, **kwargs: Any) -> int:
        """Stream record batches into one CSV file; returns the rows written."""
        schema = reader.schema
        _check_writable(schema)
        path = Path(destination)
        flat_schema = _flat_schema(schema)
        total = 0
        with default_audit_logger.track(
            operation="csv_write_stream", source="sink", destination=str(path)
        ) as tracker:
            with (
                atomic_write(path) as part,
                part.open("wb") as handle,
                pacsv.CSVWriter(handle, flat_schema) as writer,
            ):
                for batch in reader:
                    writer.write_table(pa.Table.from_batches([batch]).cast(flat_schema))
                    total += batch.num_rows
            _write_sidecar(path, schema)
            tracker.set_records(total)
        return total


def read_csv_typed(path: Path | str) -> pa.Table:
    """Read a CSV written by :class:`CsvSink` back with exactly its Arrow schema.

    Raises ``FileNotFoundError`` without the sidecar and ``ValueError`` when the file header does not
    match the sidecar.
    """
    csv_path = Path(path)
    side = sidecar_path(csv_path)
    if not side.exists():
        raise FileNotFoundError(f"no schema sidecar {side.name} next to {csv_path.name}")
    info = json.loads(side.read_text(encoding="utf-8"))
    schema = pa.ipc.read_schema(pa.py_buffer(base64.b64decode(info["arrow_ipc_schema_base64"])))
    with csv_path.open("r", encoding="utf-8") as handle:
        header = handle.readline().strip().replace('"', "").split(",")
    if header != schema.names:
        raise ValueError(
            f"CSV header {header} does not match the schema sidecar columns {schema.names}"
        )
    flat = _flat_schema(schema)
    table = pacsv.read_csv(
        csv_path,
        convert_options=pacsv.ConvertOptions(
            column_types={f.name: f.type for f in flat},
            null_values=[""],
            strings_can_be_null=True,
        ),
    )
    return table.cast(schema)


__all__ = ["SCHEMA_FORMAT", "CsvSink", "read_csv_typed", "sidecar_path"]
