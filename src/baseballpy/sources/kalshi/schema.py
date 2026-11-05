"""Strict Arrow schemas of the Kalshi datasets (from the generated ``tables.py``)."""

import pyarrow as pa

from baseballpy.core.schema_tools import schema_from_columns
from baseballpy.sources.kalshi.endpoints import DATASET_KEYS
from baseballpy.sources.kalshi.tables import KALSHI_COLUMNS

#: dataset -> typed columns plus the trailing ``_extras`` JSON column for keys the probe has not seen
KALSHI_SCHEMAS: dict[str, pa.Schema] = {
    dataset: schema_from_columns(columns) for dataset, columns in KALSHI_COLUMNS.items()
}

#: dataset -> primary key columns
KALSHI_KEYS: dict[str, tuple[str, ...]] = dict(DATASET_KEYS)

__all__ = ["KALSHI_KEYS", "KALSHI_SCHEMAS"]
