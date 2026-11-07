"""Strict Arrow schemas of the Baseball-Reference WAR datasets (from the generated ``tables.py``)."""

import pyarrow as pa

from baseballpy.core.schema_tools import schema_from_columns
from baseballpy.sources.bref.endpoints import DATASET_KEYS
from baseballpy.sources.bref.tables import BREF_COLUMNS

#: dataset -> typed columns plus the trailing ``_extras`` JSON column for headers not seen yet
BREF_SCHEMAS: dict[str, pa.Schema] = {
    dataset: schema_from_columns(columns) for dataset, columns in BREF_COLUMNS.items()
}

#: dataset -> primary key columns
BREF_KEYS: dict[str, tuple[str, ...]] = dict(DATASET_KEYS)

__all__ = ["BREF_KEYS", "BREF_SCHEMAS"]
