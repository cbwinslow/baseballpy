"""DuckDB storage sink for zero-copy Arrow ingestion (append, replace, keyed upsert)."""

import logging
from collections.abc import Sequence
from typing import Any

import duckdb
import pyarrow as pa

from baseballpy.core.audit import default_audit_logger
from baseballpy.core.sql import quote_ident

logger = logging.getLogger(__name__)

SOURCE_VIEW = "_baseballpy_src"
MODES = ("append", "replace", "upsert")


class DuckDBSink:
    """Ingests Arrow Tables and RecordBatches directly into DuckDB without pandas conversion."""

    @staticmethod
    def _table_exists(con: duckdb.DuckDBPyConnection, name: str) -> bool:
        schema, _, table = name.rpartition(".")
        row = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = ? AND table_schema = ?",
            [table, schema or "main"],
        ).fetchone()
        return bool(row and row[0] > 0)

    @staticmethod
    def _add_missing_columns(con: duckdb.DuckDBPyConnection, name: str, ident: str) -> None:
        existing = {row[0] for row in con.execute(f"DESCRIBE {ident}").fetchall()}  # noqa: S608
        for col_name, col_type, *_ in con.execute(
            f"DESCRIBE SELECT * FROM {SOURCE_VIEW}"
        ).fetchall():  # noqa: S608
            if col_name not in existing:
                logger.warning("schema drift: adding column %s to %s", col_name, name)
                con.execute(
                    f"ALTER TABLE {ident} ADD COLUMN {quote_ident(col_name)} {col_type}"  # noqa: S608
                )

    def _write_table(
        self,
        con: duckdb.DuckDBPyConnection,
        table: pa.Table,
        table_name: str,
        mode: str,
        key_columns: Sequence[str] | None,
    ) -> int:
        ident = quote_ident(table_name)
        if mode not in MODES:
            raise ValueError(f"Unsupported mode: {mode}. Use one of {MODES}.")
        keys = [quote_ident(k) for k in key_columns or ()]
        if mode == "upsert" and not keys:
            raise ValueError("upsert mode requires key_columns")
        missing = [k for k in key_columns or () if k not in table.column_names]
        if missing:
            raise ValueError(f"key columns not in table: {missing}")

        con.register(SOURCE_VIEW, table)
        try:
            exists = self._table_exists(con, table_name)
            if mode == "replace":
                con.execute(f"CREATE OR REPLACE TABLE {ident} AS SELECT * FROM {SOURCE_VIEW}")  # noqa: S608
                return len(table)
            if len(table) == 0:
                return 0
            if not exists:
                select = (
                    f"SELECT DISTINCT ON ({', '.join(keys)}) * FROM {SOURCE_VIEW}"  # noqa: S608
                    if mode == "upsert"
                    else f"SELECT * FROM {SOURCE_VIEW}"  # noqa: S608
                )
                con.execute(f"CREATE TABLE {ident} AS {select}")
                if mode == "upsert":
                    con.execute(
                        f"CREATE UNIQUE INDEX IF NOT EXISTS {quote_ident('uq_' + table_name.replace('.', '_'))} "  # noqa: S608
                        f"ON {ident} ({', '.join(keys)})"
                    )
                return len(table)
            self._add_missing_columns(con, table_name, ident)
            if mode == "append":
                con.execute(f"INSERT INTO {ident} BY NAME SELECT * FROM {SOURCE_VIEW}")  # noqa: S608
            else:
                con.execute(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {quote_ident('uq_' + table_name.replace('.', '_'))} "  # noqa: S608
                    f"ON {ident} ({', '.join(keys)})"
                )
                con.execute(
                    f"INSERT OR REPLACE INTO {ident} BY NAME "  # noqa: S608
                    f"SELECT DISTINCT ON ({', '.join(keys)}) * FROM {SOURCE_VIEW}"
                )
            return len(table)
        finally:
            con.unregister(SOURCE_VIEW)

    def write(
        self,
        table: pa.Table,
        destination: str,
        table_name: str = "pitches",
        mode: str = "append",
        key_columns: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> int:
        """Write a PyArrow Table into a DuckDB database file or in-memory database."""
        quote_ident(table_name)  # fail fast, before any connection or audit event
        with default_audit_logger.track(
            operation="duckdb_write",
            source="sink",
            destination=f"{destination}:{table_name}",
        ) as tracker:
            con = duckdb.connect(database=destination)
            try:
                written = self._write_table(con, table, table_name, mode, key_columns)
            finally:
                con.close()
            tracker.set_records(written)
            return written

    def write_stream(
        self,
        reader: pa.RecordBatchReader,
        destination: str,
        table_name: str = "pitches",
        mode: str = "append",
        key_columns: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> int:
        """Stream record batches into DuckDB over a single connection and one audit event."""
        quote_ident(table_name)
        with default_audit_logger.track(
            operation="duckdb_write_stream",
            source="sink",
            destination=f"{destination}:{table_name}",
        ) as tracker:
            con = duckdb.connect(database=destination)
            total = 0
            first = True
            try:
                for batch in reader:
                    batch_mode = (
                        "replace"
                        if first and mode == "replace"
                        else ("append" if mode == "replace" else mode)
                    )
                    total += self._write_table(
                        con, pa.Table.from_batches([batch]), table_name, batch_mode, key_columns
                    )
                    first = False
                if first and mode == "replace":
                    empty = reader.schema.empty_table()
                    self._write_table(con, empty, table_name, "replace", key_columns)
            finally:
                con.close()
            tracker.set_records(total)
            return total
