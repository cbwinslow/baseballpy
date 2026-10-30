"""Data-quality checks for Retrosheet datasets: duplicate keys and player ids that point nowhere.

Findings are warnings, never errors. The relationships are one declarative table
(:data:`FOREIGN_KEYS`) checked by one generic function, after every dataset of a season is stored, so
the result does not depend on the order the datasets were written in. Parents are named
``<source>.<dataset>``: a Retrosheet roster of the same season, or the Chadwick register (cross-source
ids, by registry name only, so no source imports another).
"""

from collections.abc import Callable
from dataclasses import dataclass

import pyarrow as pa

from baseballpy.core.quality import duplicate_rows, orphan_rows

#: prefix of the finding keys written by the relationship checks
ORPHAN_PREFIX = "orphan_rows:"
ROSTERS = "retrosheet.rosters"
REGISTER = "chadwick.register"


@dataclass(frozen=True)
class ForeignKey:
    """Rows of ``child`` whose ``columns`` have no match in ``parent.parent_columns``."""

    child: str
    columns: tuple[str, ...]
    parent: str
    parent_columns: tuple[str, ...]

    @property
    def label(self) -> str:
        """The finding key, for example ``orphan_rows:BAT_ID->retrosheet.rosters``."""
        return f"{ORPHAN_PREFIX}{'+'.join(self.columns)}->{self.parent}"


FOREIGN_KEYS: tuple[ForeignKey, ...] = (
    ForeignKey("events", ("BAT_ID",), ROSTERS, ("player_id",)),
    ForeignKey("events", ("PIT_ID",), ROSTERS, ("player_id",)),
    ForeignKey("events_postseason", ("BAT_ID",), ROSTERS, ("player_id",)),
    ForeignKey("events_postseason", ("PIT_ID",), ROSTERS, ("player_id",)),
    ForeignKey("boxscores_batting", ("player_id",), ROSTERS, ("player_id",)),
    ForeignKey("boxscores_pitching", ("pitcher_id",), ROSTERS, ("player_id",)),
    ForeignKey("daily_splits", ("PLAYER_ID",), ROSTERS, ("player_id",)),
    ForeignKey("substitutions", ("SUB_ID",), ROSTERS, ("player_id",)),
    ForeignKey("rosters", ("player_id",), REGISTER, ("key_retro",)),
)


def columns_needed(dataset: str, key: tuple[str, ...]) -> list[str]:
    """The columns of ``dataset`` the checks read (so a wide table is read column-wise)."""
    wanted = list(key)
    for fk in FOREIGN_KEYS:
        if fk.child == dataset:
            wanted.extend(fk.columns)
    return list(dict.fromkeys(wanted))


def quality_report(
    dataset: str,
    table: pa.Table,
    key: tuple[str, ...],
    parents: Callable[[str], pa.Table | None],
) -> dict[str, int]:
    """Machine-readable findings for one stored chunk (empty when it looks healthy).

    ``parents`` returns the parent table for ``<source>.<dataset>`` or ``None`` when it is not
    stored or has no rows (nothing to compare with, so no finding).
    """
    findings: dict[str, int] = {}
    if duplicates := duplicate_rows(table, key):
        findings["duplicate_key_rows"] = duplicates
    for fk in FOREIGN_KEYS:
        if fk.child != dataset or not set(fk.columns) <= set(table.column_names):
            continue
        parent = parents(fk.parent)
        if parent is None or not set(fk.parent_columns) <= set(parent.column_names):
            continue
        if count := orphan_rows(table, fk.columns, parent, fk.parent_columns):
            findings[fk.label] = count
    return findings
