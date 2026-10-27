"""Apache Parquet storage sink: atomic single-file and Hive-partitioned dataset writes."""

import os
import shutil
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import atomic_write, atomic_write_parquet
from baseballpy.core.audit import default_audit_logger


class ParquetSink:
    """Writes PyArrow Tables and RecordBatches to compressed Parquet files atomically."""

    def write(
        self,
        table: pa.Table,
        destination: str,
        compression: str = "zstd",
        partition_by: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> int:
        """Write a table to one Parquet file, or a Hive-partitioned dataset if ``partition_by``."""
        num_rows = len(table)
        if num_rows == 0:
            return 0

        path = Path(destination)
        with default_audit_logger.track(
            operation="parquet_write",
            source="sink",
            destination=str(path),
        ) as tracker:
            if partition_by:
                self._write_partitioned(table, path, compression, list(partition_by))
            else:
                atomic_write_parquet(table, path, compression=compression)
            tracker.set_records(num_rows)
            return num_rows

    @staticmethod
    def _write_partitioned(
        table: pa.Table, root: Path, compression: str, partition_by: list[str]
    ) -> None:
        """Write the dataset to a temp directory, then move files into place atomically."""
        root.mkdir(parents=True, exist_ok=True)
        staging = root.parent / f".{root.name}.staging-{uuid.uuid4().hex[:8]}"
        try:
            pq.write_to_dataset(
                table,
                root_path=str(staging),
                partition_cols=partition_by,
                compression=compression,
                basename_template="part-{i}.parquet",
                existing_data_behavior="overwrite_or_ignore",
            )
            for produced in staging.rglob("*.parquet"):
                target = root / produced.relative_to(staging)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(produced, target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def write_stream(
        self,
        reader: pa.RecordBatchReader,
        destination: str,
        compression: str = "zstd",
        partition_by: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> int:
        """Stream record batches into one Parquet file (row-group batches, atomic)."""
        if partition_by:
            return self.write(
                reader.read_all(), destination, compression=compression, partition_by=partition_by
            )
        path = Path(destination)
        total = 0
        with default_audit_logger.track(
            operation="parquet_write_stream", source="sink", destination=str(path)
        ) as tracker:
            with atomic_write(path) as part_path:
                writer = pq.ParquetWriter(part_path, reader.schema, compression=compression)
                try:
                    for batch in reader:
                        writer.write_batch(batch)
                        total += batch.num_rows
                finally:
                    writer.close()
            tracker.set_records(total)
        return total
