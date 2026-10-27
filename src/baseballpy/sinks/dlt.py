"""dlt sink bridging PyArrow tables into relational databases and cloud warehouses."""

from collections.abc import Sequence
from typing import Any

import dlt
import pyarrow as pa

SUPPORTED_DESTINATIONS = ("duckdb", "postgres", "snowflake", "bigquery", "motherduck")


class DltSink:
    """Sink that streams PyArrow Tables into warehouses via dlt (append, replace or merge)."""

    def __init__(
        self,
        pipeline: dlt.Pipeline | None = None,
        pipeline_name: str = "baseballpy_pipeline",
        destination: str = "duckdb",
        dataset_name: str = "baseballpy_data",
    ) -> None:
        if pipeline is None and destination not in SUPPORTED_DESTINATIONS:
            raise ValueError(f"destination must be one of {SUPPORTED_DESTINATIONS}")
        self.pipeline = pipeline or dlt.pipeline(
            pipeline_name=pipeline_name,
            destination=destination,
            dataset_name=dataset_name,
        )
        self.last_load_info: Any = None

    def write(
        self,
        table: pa.Table,
        destination: str,
        write_disposition: str = "append",
        primary_key: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> int:
        """Load ``table`` into the dlt resource ``destination``; returns rows loaded."""
        if write_disposition not in ("append", "replace", "merge"):
            raise ValueError(f"unsupported write_disposition {write_disposition!r}")
        if write_disposition == "merge" and not primary_key:
            raise ValueError("merge disposition requires primary_key")
        resource_factory: Any = dlt.resource
        resource = resource_factory(
            [table],
            name=destination,
            write_disposition=write_disposition,
            primary_key=list(primary_key) if primary_key else None,
        )
        self.last_load_info = self.pipeline.run(resource, **kwargs)
        return len(table)

    def write_stream(self, reader: pa.RecordBatchReader, destination: str, **kwargs: Any) -> int:
        """Load a record-batch stream (batches are passed to dlt as Arrow tables)."""
        total = 0
        first = True
        disposition = kwargs.pop("write_disposition", "append")
        for batch in reader:
            total += self.write(
                pa.Table.from_batches([batch]),
                destination,
                write_disposition="replace"
                if first and disposition == "replace"
                else ("append" if disposition == "replace" else disposition),
                **kwargs,
            )
            first = False
        return total
