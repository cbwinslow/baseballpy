"""Apache Parquet storage sink with partitioning support."""

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.audit import default_audit_logger


class ParquetSink:
    """Writes PyArrow Tables and RecordBatches to compressed Parquet files."""

    def write(
        self,
        table: pa.Table,
        destination: str,
        compression: str = "snappy",
        **kwargs: Any,
    ) -> int:
        """Write a PyArrow Table to a Parquet file."""
        num_rows = len(table)
        if num_rows == 0:
            return 0

        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)

        with default_audit_logger.track(
            operation="parquet_write",
            source="sink",
            destination=str(path),
        ) as tracker:
            pq.write_table(table, path, compression=compression)
            tracker.set_records(num_rows)
            return num_rows

    def write_stream(
        self,
        reader: pa.RecordBatchReader,
        destination: str,
        compression: str = "snappy",
        **kwargs: Any,
    ) -> int:
        """Stream record batches into a single Parquet file."""
        table = reader.read_all()
        return self.write(table, destination=destination, compression=compression, **kwargs)
