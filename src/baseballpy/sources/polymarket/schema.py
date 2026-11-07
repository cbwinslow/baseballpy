"""Strict Arrow schemas of the Polymarket datasets (from the generated ``tables.py``)."""

import pyarrow as pa

from baseballpy.core.schema_tools import schema_from_columns
from baseballpy.sources.polymarket.endpoints import DATASET_KEYS
from baseballpy.sources.polymarket.tables import POLYMARKET_COLUMNS

#: dataset -> typed columns plus the trailing ``_extras`` JSON column for keys the probe has not seen
POLYMARKET_SCHEMAS: dict[str, pa.Schema] = {
    dataset: schema_from_columns(columns) for dataset, columns in POLYMARKET_COLUMNS.items()
}

#: dataset -> primary key columns
POLYMARKET_KEYS: dict[str, tuple[str, ...]] = dict(DATASET_KEYS)

__all__ = ["POLYMARKET_KEYS", "POLYMARKET_SCHEMAS"]
