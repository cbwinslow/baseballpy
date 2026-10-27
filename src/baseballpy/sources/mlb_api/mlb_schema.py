"""Strict PyArrow schemas of the declarative MLB endpoints (from the generated ``mlb_tables``)."""

import pyarrow as pa

from baseballpy.core.schema_tools import schema_from_columns
from baseballpy.sources.mlb_api.mlb_tables import MLB_COLUMNS

#: endpoint name -> schema (typed columns, ``upstream`` metadata = flattened key, trailing ``_extras``)
MLB_SCHEMAS: dict[str, pa.Schema] = {
    name: schema_from_columns(columns) for name, columns in MLB_COLUMNS.items()
}
