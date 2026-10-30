"""Generic data-quality helpers shared by the sources: duplicate keys and orphan rows.

A source declares its relationships as a table and calls these functions; nothing here knows a
dataset name.
"""

import pyarrow as pa
import pyarrow.compute as pc


def duplicate_rows(table: pa.Table, key: tuple[str, ...]) -> int:
    """Rows beyond the first for each duplicated ``key`` (0 when unique, empty or a column is missing)."""
    if not key or table.num_rows == 0 or any(k not in table.column_names for k in key):
        return 0
    counts = table.group_by(list(key)).aggregate([([key[0]], "count")])
    return int(pc.sum(pc.subtract(counts.column(counts.num_columns - 1), 1)).as_py() or 0)


def orphan_rows(
    table: pa.Table,
    columns: tuple[str, ...],
    parent: pa.Table,
    parent_columns: tuple[str, ...],
) -> int:
    """Rows of ``table`` whose ``columns`` (all present) match no row of ``parent``.

    Rows with an empty value in any of the columns are not orphans (nothing points anywhere).
    """
    if table.num_rows == 0:
        return 0
    present = None
    for column in columns:
        valid = pc.is_valid(table[column])
        present = valid if present is None else pc.and_(present, valid)
    child = table.select(list(columns)).filter(present)
    if child.num_rows == 0:
        return 0
    keys = parent.select(list(parent_columns)).rename_columns(list(columns)).cast(child.schema)
    return int(child.join(keys, keys=list(columns), join_type="left anti").num_rows)
