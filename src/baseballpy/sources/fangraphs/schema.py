"""Strict Arrow schemas of the FanGraphs datasets (from the generated ``tables.py``)."""

import pyarrow as pa

from baseballpy.core.schema_tools import schema_from_columns
from baseballpy.sources.fangraphs.files import DATASET_KEYS
from baseballpy.sources.fangraphs.tables import FANGRAPHS_COLUMNS

#: dataset -> typed columns plus the trailing ``_extras`` JSON column for headers not seen yet
FANGRAPHS_SCHEMAS: dict[str, pa.Schema] = {
    dataset: schema_from_columns(columns) for dataset, columns in FANGRAPHS_COLUMNS.items()
}

#: dataset -> primary key columns
FANGRAPHS_KEYS: dict[str, tuple[str, ...]] = dict(DATASET_KEYS)

__all__ = ["FANGRAPHS_KEYS", "FANGRAPHS_SCHEMAS"]
