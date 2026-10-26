"""dlt sink bridging PyArrow tables into relational databases and cloud warehouses."""

from typing import Any

import dlt
import pyarrow as pa


class DltSink:
    """Sink that streams PyArrow Tables into cloud/relational warehouses via dlt."""

    def __init__(
        self,
        pipeline: dlt.Pipeline | None = None,
        pipeline_name: str = "baseballpy_pipeline",
    ) -> None:
        self.pipeline = pipeline or dlt.pipeline(
            pipeline_name=pipeline_name,
            destination="duckdb",
            dataset_name="baseballpy_data",
        )

    def write(
        self,
        data: pa.Table,
        destination: str,
        write_disposition: Any = "append",
        **kwargs: Any,
    ) -> Any:
        """Stream PyArrow table into dlt destination."""
        res = dlt.resource(
            [data],
            name=destination,
            write_disposition=write_disposition,
        )
        load_info = self.pipeline.run(res, **kwargs)
        return load_info
