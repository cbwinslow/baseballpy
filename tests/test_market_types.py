"""Exact decimals and JSON records: the typing building blocks of the market sources."""

import decimal
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baseballpy.core.atomic import atomic_write_parquet
from baseballpy.core.quarantine import Quarantine, QuarantineConfig
from baseballpy.core.schema_tools import (
    EXTRAS,
    normalize_records,
    pa_type,
    schema_from_columns,
)

SCHEMA = schema_from_columns(
    [
        ("ticker", "string"),
        ("yes_price", "decimal(9,4)"),
        ("count", "decimal(18,2)"),
        ("created_time", "timestamp"),
        ("is_block_trade", "bool"),
        ("price_ranges", "string"),
        ("exchange_index", "int16"),
    ]
)


def _quarantine(tmp_path: Path) -> Quarantine:
    return Quarantine(QuarantineConfig(quarantine_dir_override=tmp_path / "quarantine"))


def test_decimal_type_names_give_exact_fixed_point_types() -> None:
    assert pa_type("decimal(9,4)") == pa.decimal128(9, 4)
    assert pa_type("decimal(18,2)") == pa.decimal128(18, 2)
    for bad in ("decimal(4,9)", "decimal(40,2)", "decimal(9)", "decimal(9,0)"):
        with pytest.raises(ValueError):
            pa_type(bad)


def test_records_become_typed_columns_and_nothing_is_lost(tmp_path: Path) -> None:
    records = [
        {
            "ticker": "KXMLBGAME-26OCT28MILTB-MIL",
            "yes_price": "0.4400",
            "count": "1200.50",
            "created_time": "2026-10-28T20:00:01.123456Z",
            "is_block_trade": False,
            "price_ranges": [{"start": "0.00", "end": "1.00"}],
            "exchange_index": 0,
            "brand_new_field": "x",
        },
        {"ticker": "B", "yes_price": None},
    ]
    table = normalize_records(
        records, SCHEMA, source="kalshi", dataset="trades", quarantine=_quarantine(tmp_path)
    )
    assert table.schema.names == [*SCHEMA.names[:-1], EXTRAS]
    assert table.schema.field("yes_price").type == pa.decimal128(9, 4)
    first = table.slice(0, 1).to_pylist()[0]
    assert first["yes_price"] == decimal.Decimal("0.4400")
    assert first["count"] == decimal.Decimal("1200.50")
    assert first["is_block_trade"] is False
    assert first["price_ranges"] == '[{"end":"1.00","start":"0.00"}]'
    assert first["exchange_index"] == 0
    assert first["created_time"].microsecond == 123456
    assert first[EXTRAS] == '{"brand_new_field": "x"}'
    second = table.slice(1, 1).to_pylist()[0]
    assert second["yes_price"] is None and second[EXTRAS] is None


def test_an_uncastable_value_is_quarantined_not_silently_nulled(tmp_path: Path) -> None:
    quarantine = _quarantine(tmp_path)
    table = normalize_records(
        [{"ticker": "A", "yes_price": "0.4400"}, {"ticker": "B", "yes_price": "n/a"}],
        SCHEMA,
        source="kalshi",
        dataset="trades",
        quarantine=quarantine,
    )
    assert table.column("yes_price").to_pylist() == [decimal.Decimal("0.4400"), None]
    assert list((tmp_path / "quarantine").rglob("*")), "the bad cell must be written to quarantine"


def test_decimal_columns_are_stored_as_integers_and_duckdb_reads_them(tmp_path: Path) -> None:
    prices = [decimal.Decimal("0.4400")] * 1000 + [decimal.Decimal("0.0100")] * 1000
    table = pa.table({"p": pa.array(prices, pa.decimal128(9, 4))})
    target = tmp_path / "part.parquet"
    atomic_write_parquet(table, target, compression="zstd")
    assert "int32" in str(pq.ParquetFile(target).schema)
    got = duckdb.sql(
        f"select sum(p), typeof(any_value(p)) from read_parquet('{target.as_posix()}')"
    ).fetchall()[0]
    assert got == (decimal.Decimal("440.0000") + decimal.Decimal("10.0000"), "DECIMAL(9,4)")
