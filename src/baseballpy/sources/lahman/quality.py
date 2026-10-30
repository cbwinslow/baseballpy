"""Data-quality checks for Lahman tables: duplicate keys, stale data and orphan rows.

Findings are warnings, never errors. The relationships between tables are one declarative table
(:data:`FOREIGN_KEYS`) checked by one generic function, so every id column that points into another
table is covered the same way, whatever order the tables were stored in (the caller rechecks the
children of a table when that table arrives later).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import pyarrow as pa
import pyarrow.compute as pc

from baseballpy.core.quality import duplicate_rows, orphan_rows
from baseballpy.sources.lahman.schema import LAHMAN_PRIMARY_KEYS

#: tables whose newest yearID shows whether the release is current
FRESHNESS_TABLES = {"Batting": "yearID", "Teams": "yearID"}
#: prefix of the finding keys written by the relationship checks
ORPHAN_PREFIX = "orphan_rows:"


@dataclass(frozen=True)
class ForeignKey:
    """Rows of ``child`` whose ``columns`` have no match in ``parent.parent_columns``."""

    #: a table name, or ``None`` for every table that has all the columns
    child: str | None
    columns: tuple[str, ...]
    parent: str
    parent_columns: tuple[str, ...]

    @property
    def label(self) -> str:
        """The finding key, for example ``orphan_rows:playerID->People``."""
        return f"{ORPHAN_PREFIX}{'+'.join(self.columns)}->{self.parent}"

    def applies_to(self, table_name: str, column_names: list[str]) -> bool:
        """Whether a table is a child of this relationship."""
        return (
            self.child in (None, table_name)
            and table_name != self.parent
            and set(self.columns) <= set(column_names)
        )


FOREIGN_KEYS: tuple[ForeignKey, ...] = (
    ForeignKey(None, ("playerID",), "People", ("playerID",)),
    ForeignKey(None, ("yearID", "teamID"), "Teams", ("yearID", "teamID")),
    ForeignKey("Teams", ("franchID",), "TeamsFranchises", ("franchID",)),
    ForeignKey("HomeGames", ("parkkey",), "Parks", ("parkkey",)),
    ForeignKey("CollegePlaying", ("schoolID",), "Schools", ("schoolID",)),
)
#: tables that are the parent of some relationship
PARENT_TABLES = frozenset(fk.parent for fk in FOREIGN_KEYS)


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
    return duplicate_rows(table, tuple(LAHMAN_PRIMARY_KEYS.get(name) or ()))


def foreign_key_findings(
    name: str,
    table: pa.Table,
    parents: Callable[[str], pa.Table | None],
) -> dict[str, int]:
    """Orphan counts for every relationship ``table`` is a child of; parents not stored are skipped."""
    findings: dict[str, int] = {}
    for fk in FOREIGN_KEYS:
        if not fk.applies_to(name, table.column_names):
            continue
        parent = parents(fk.parent)
        if parent is None or not set(fk.parent_columns) <= set(parent.column_names):
            continue
        if count := orphan_rows(table, fk.columns, parent, fk.parent_columns):
            findings[fk.label] = count
    return findings


def quality_report(
    name: str,
    table: pa.Table,
    *,
    parents: Callable[[str], pa.Table | None],
    today: date,
) -> dict[str, int | str]:
    """Machine-readable findings (empty when the table looks healthy)."""
    findings: dict[str, int | str] = {}
    if (dupes := duplicate_key_rows(name, table)) > 0:
        findings["duplicate_key_rows"] = dupes
    findings.update(foreign_key_findings(name, table, parents))
    if (stale := stale_year_warning(name, table, today)) is not None:
        findings["stale"] = stale
    return findings
