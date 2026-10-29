"""dlt sink bridging PyArrow tables into relational databases and cloud warehouses.

``dlt`` creates the tables, maps the types and merges on the primary key; our Arrow schema stays the
contract: :meth:`DltSink.table_info` reads back what the database holds and :func:`type_mismatches`
compares the column types with the schema (a ``float`` column becomes ``double`` and ``int8`` a
``smallint`` or ``tinyint``; those widenings lose nothing and are accepted, anything else is reported).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import dlt
import pyarrow as pa

SUPPORTED_DESTINATIONS = ("duckdb", "postgres", "snowflake", "bigquery", "motherduck")

_TEXT = frozenset({"varchar", "character varying", "text", "string"})


def allowed_sql_types(arrow_type: pa.DataType) -> frozenset[str]:
    """SQL type names (lower case, as ``information_schema`` reports them) accepted for a column."""
    if pa.types.is_dictionary(arrow_type):
        return allowed_sql_types(arrow_type.value_type)
    if pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type):
        return _TEXT
    if pa.types.is_boolean(arrow_type):
        return frozenset({"boolean", "bool"})
    if pa.types.is_int8(arrow_type):
        return frozenset({"tinyint", "smallint"})
    if pa.types.is_int16(arrow_type):
        return frozenset({"smallint"})
    if pa.types.is_int32(arrow_type):
        return frozenset({"integer", "int"})
    if pa.types.is_int64(arrow_type):
        return frozenset({"bigint"})
    if pa.types.is_float32(arrow_type):
        return frozenset({"real", "float", "double", "double precision"})  # widened, lossless
    if pa.types.is_float64(arrow_type):
        return frozenset({"double", "double precision"})
    if pa.types.is_date(arrow_type):
        return frozenset({"date"})
    if pa.types.is_timestamp(arrow_type):
        if arrow_type.tz is not None:
            return frozenset({"timestamp with time zone", "timestamptz"})
        return frozenset({"timestamp", "timestamp without time zone"})
    return frozenset()


def type_mismatches(schema: pa.Schema, columns: Mapping[str, str]) -> list[str]:
    """Human-readable differences between ``schema`` and the database column types (empty = same).

    Column order and names must match exactly; ``dlt`` bookkeeping columns (``_dlt_*``) are ignored.
    """
    actual = {name: ty for name, ty in columns.items() if not name.startswith("_dlt_")}
    problems: list[str] = []
    if list(actual) != schema.names:
        problems.append(f"columns differ: database has {list(actual)}, schema has {schema.names}")
        return problems
    for field in schema:
        sql_type = actual[field.name].lower()
        if sql_type.startswith("enum"):  # a DuckDB ENUM holds text
            sql_type = "varchar"
        if sql_type not in allowed_sql_types(field.type):
            problems.append(f"{field.name}: arrow {field.type} became database type {sql_type}")
    return problems


@dataclass(frozen=True)
class TableInfo:
    """What the database holds for one table: row count and ``column -> SQL type`` in order."""

    rows: int
    columns: dict[str, str]


class DltSink:
    """Sink that streams PyArrow Tables into warehouses via dlt (append, replace or merge)."""

    def __init__(
        self,
        pipeline: dlt.Pipeline | None = None,
        pipeline_name: str = "baseballpy_pipeline",
        destination: str = "duckdb",
        dataset_name: str = "baseballpy_data",
        credentials: str | None = None,
        pipelines_dir: str | None = None,
    ) -> None:
        if pipeline is None and destination not in SUPPORTED_DESTINATIONS:
            raise ValueError(f"destination must be one of {SUPPORTED_DESTINATIONS}")
        self.dataset_name = dataset_name
        target: Any = destination
        if pipeline is None:
            # "direct" keeps every identifier exactly as our Arrow schema spells it; dlt's default
            # would rewrite playerID to player_id and 2B to _2_b, so the tables would not match
            options_for_destination: dict[str, Any] = {"naming_convention": "direct"}
            if credentials is not None:
                options_for_destination["credentials"] = credentials
            target = getattr(dlt.destinations, destination)(**options_for_destination)
        options: dict[str, Any] = {} if pipelines_dir is None else {"pipelines_dir": pipelines_dir}
        self.pipeline = pipeline or dlt.pipeline(
            pipeline_name=pipeline_name,
            destination=target,
            dataset_name=dataset_name,
            **options,
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
        """Load ``table`` into the dlt resource ``destination``; returns rows loaded.

        ``merge`` needs ``primary_key`` (re-loading the same keys updates rows, never duplicates).
        Key columns are declared not-null.
        """
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
            columns={key: {"nullable": False} for key in primary_key} if primary_key else None,
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

    def table_info(self, table_name: str) -> TableInfo:
        """Row count and column types of ``table_name`` as the database reports them."""
        with self.pipeline.sql_client() as client:
            columns = client.execute_sql(
                "select column_name, data_type from information_schema.columns "
                "where table_schema = %s and table_name = %s order by ordinal_position",
                self.dataset_name,
                table_name,
            )
            qualified = client.make_qualified_table_name(table_name)  # escaped by dlt
            counted = client.execute_sql(f"select count(*) from {qualified}")  # noqa: S608
        if not columns or not counted:
            raise LookupError(f"table {self.dataset_name}.{table_name} does not exist")
        return TableInfo(rows=int(counted[0][0]), columns={name: ty for name, ty in columns})
