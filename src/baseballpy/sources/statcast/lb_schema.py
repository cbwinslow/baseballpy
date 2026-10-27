"""Strict PyArrow schemas for every supported Savant leaderboard variant (from ``lb_tables.py``)."""

import pyarrow as pa

from baseballpy.core.schema_tools import schema_from_columns
from baseballpy.sources.statcast.lb_catalog import BY_SLUG, SUPPORTED
from baseballpy.sources.statcast.lb_tables import LEADERBOARD_COLUMNS, LEADERBOARD_META

#: slug -> strict schema (typed columns + trailing ``_extras`` JSON string for unknown columns)
LEADERBOARD_SCHEMAS: dict[str, pa.Schema] = {
    slug: schema_from_columns(columns) for slug, columns in LEADERBOARD_COLUMNS.items()
}


def missing_schemas() -> list[str]:
    """Supported variants that have no generated schema (must be empty; asserted by tests)."""
    return [d.slug for d in SUPPORTED if d.slug not in LEADERBOARD_SCHEMAS]


def min_year(slug: str) -> int | None:
    """First season with data recorded by the live probe (``None`` for flat snapshots)."""
    if BY_SLUG[slug].year_style == "none":
        return None
    value = LEADERBOARD_META[slug]["min_year"]
    return int(value) if value is not None else None


def default_min(slug: str) -> str | None:
    """The widest ``min`` qualifier found by the probe (``None`` if the route has none)."""
    value = LEADERBOARD_META[slug]["min"]
    return str(value) if value is not None else None
