"""Data-quality checks for Lahman tables: warnings only, never errors."""

from datetime import date

import pyarrow as pa
import pyarrow.compute as pc

from baseballpy.sources.lahman.schema import LAHMAN_PRIMARY_KEYS

#: Tables whose newest ``yearID`` tells whether the release is current.
FRESHNESS_TABLES = {"Batting": "yearID", "Teams": "yearID"}


def last_completed_season(today: date) -> int:
    """The last MLB season that is certainly over (the next one starts in spring)."""
    return today.year if today.month >= 11 else today.year - 1


def stale_year_warning(name: str, table: pa.Table, today: date) -> str | None:
    """Warn when the newest ``yearID`` is more than one season behind the last completed one."""
    column = FRESHNESS_TABLES.get(name)
    if column is None or column not in table.column_names or table.num_rows == 0:
        return None
    newest = pc.max(table[column]).as_py()
    if newest is None:
        return None
    expected = last_completed_season(today)
    if int(newest) < expected - 1:
        return (
            f"Lahman {name} data ends at {newest} but the last completed MLB season is {expected}; "
            "the configured source looks stale (see LahmanSource.import_archive or "
            "BASEBALLPY_LAHMAN_REPO)."
        )
    return None


def duplicate_key_rows(name: str, table: pa.Table) -> int:
    """Rows beyond the first for each duplicated primary key (0 when unique or key unknown)."""
    key = LAHMAN_PRIMARY_KEYS.get(name)
    if not key or table.num_rows == 0 or any(k not in table.column_names for k in key):
        return 0
    counts = table.group_by(list(key)).aggregate([([key[0]], "count")])
    return int(pc.sum(pc.subtract(counts.column(counts.num_columns - 1), 1)).as_py() or 0)


def orphan_player_rows(table: pa.Table, people_ids: pa.ChunkedArray | pa.Array) -> int:
    """Rows whose ``playerID`` is not present in ``People`` (foreign-key sanity)."""
    if "playerID" not in table.column_names or table.num_rows == 0:
        return 0
    mask = pc.invert(pc.is_in(table["playerID"], value_set=pa.array(people_ids)))
    present = pc.is_valid(table["playerID"])
    return int(pc.sum(pc.and_(mask, present).cast(pa.int64())).as_py() or 0)


def quality_report(
    name: str,
    table: pa.Table,
    *,
    people_ids: pa.ChunkedArray | pa.Array | None,
    today: date,
) -> dict[str, int | str]:
    """Machine-readable findings (empty when the table looks healthy)."""
    findings: dict[str, int | str] = {}
    if (dupes := duplicate_key_rows(name, table)) > 0:
        findings["duplicate_key_rows"] = dupes
    if (
        people_ids is not None
        and name != "People"
        and (orphans := orphan_player_rows(table, people_ids)) > 0
    ):
        findings["orphan_player_rows"] = orphans
    if (stale := stale_year_warning(name, table, today)) is not None:
        findings["stale"] = stale
    return findings
