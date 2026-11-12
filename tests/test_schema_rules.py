"""Rules about column types that the round-trip check found broken (change data-validation-roundtrip)."""

import pyarrow as pa

from baseballpy.core.datasets import DATASETS
from baseballpy.sources import catalog


def test_no_registered_column_is_a_32_bit_float() -> None:
    """A 32-bit float turns the provider's ``85.8`` into ``85.80000305175781``: decimals are 64-bit floats."""
    catalog.register_all()
    offenders = [
        f"{spec.key}.{field.name}"
        for spec in DATASETS.values()
        for field in spec.schema
        if pa.types.is_float32(field.type)
    ]
    assert offenders == [], f"use float64: {offenders[:8]}"
