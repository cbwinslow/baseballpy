"""DuckDB storage sink for zero-copy Arrow ingestion."""

from typing import Any

import duckdb
import pyarrow as pa

from baseballpy.core.audit import default_audit_logger


class DuckDBSink:
    """Ingests Arrow Tables and RecordBatches directly into DuckDB without pandas conversion."""

    def write(
        self,
        table: pa.Table,
        destination: str,
        table_name: str = "pitches",
        mode: str = "append",
        **kwargs: Any,
    ) -> int:
        """Write a PyArrow Table into a DuckDB database file or in-memory database."""
        num_rows = len(table)
        if num_rows == 0:
            return 0

        with default_audit_logger.track(
            operation="duckdb_write",
            source="sink",
            destination=f"{destination}:{table_name}",
        ) as tracker:
            con = duckdb.connect(database=destination)
            try:
                # Register table in DuckDB memory zero-copy
                con.register("_temp_arrow_table", table)

                if mode == "replace":
                    con.execute(
                        f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM _temp_arrow_table"
                    )
                elif mode == "append":
                    # Check if table exists
                    res = con.execute(
                        f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table_name}'"
                    ).fetchone()
                    table_exists = bool(res and res[0] > 0)
                    if not table_exists:
                        con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM _temp_arrow_table")
                    else:
                        con.execute(f"INSERT INTO {table_name} SELECT * FROM _temp_arrow_table")
                else:
                    raise ValueError(f"Unsupported mode: {mode}. Use 'append' or 'replace'.")
            finally:
                con.unregister("_temp_arrow_table")
                con.close()

            tracker.set_records(num_rows)
            return num_rows

    def write_stream(
        self,
        reader: pa.RecordBatchReader,
        destination: str,
        table_name: str = "pitches",
        mode: str = "append",
        **kwargs: Any,
    ) -> int:
        """Stream record batches into DuckDB."""
        total_rows = 0
        first_batch = True

        for batch in reader:
            table = pa.Table.from_batches([batch])
            batch_mode = "replace" if first_batch and mode == "replace" else "append"
            total_rows += self.write(
                table,
                destination=destination,
                table_name=table_name,
                mode=batch_mode,
                **kwargs,
            )
            first_batch = False

        return total_rows
