"""FanGraphs files the user supplies, as data (no network, no side effects).

baseballpy never downloads from FanGraphs (``docs/sources/fangraphs.md``). The user puts CSV files in
``inbox/fangraphs/`` (a one-time copy of tables they already hold, or a member's own export) and
``baseballpy ingest fangraphs`` types them. Each row of :data:`FILES` names one expected file, the
table it is copied from in the owner's homelab database, and the key of its rows.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FangraphsFile:
    """One expected file: ``<dataset>.csv`` (or ``.csv.gz``) in the inbox."""

    dataset: str
    #: table in the owner's homelab database, schema ``raw`` (the export script reads it)
    homelab_table: str
    keys: tuple[str, ...]
    description: str
    #: column whose value names the chunk (one season or one capture date per chunk);
    #: ``None`` keeps the whole table in one chunk
    chunk_by: str | None = None
    chunk_prefix: str = ""

    @property
    def names(self) -> tuple[str, ...]:
        """File names looked for in the inbox, in order."""
        return (f"{self.dataset}.csv", f"{self.dataset}.csv.gz")


FILES: tuple[FangraphsFile, ...] = (
    FangraphsFile(
        "batting",
        "fangraphs_batting",
        ("playerid", "season"),
        "FanGraphs season batting leaderboard (private research data): one row per player and season.",
        chunk_by="season",
        chunk_prefix="season-",
    ),
    FangraphsFile(
        "pitching",
        "fangraphs_pitching",
        ("playerid", "season"),
        "FanGraphs season pitching leaderboard (private research data): one row per player and season.",
        chunk_by="season",
        chunk_prefix="season-",
    ),
    FangraphsFile(
        "fielding",
        "fangraphs_fielding",
        ("playerid", "season", "pos"),
        "FanGraphs season fielding leaderboard (private research data): one row per player, season and position.",
        chunk_by="season",
        chunk_prefix="season-",
    ),
    FangraphsFile(
        "guts",
        "fangraphs_guts",
        ("season",),
        "FanGraphs Guts! constants (private research data): wOBA weights, FIP constant, run values per season.",
    ),
    FangraphsFile(
        "park_factors",
        "fangraphs_park_factors",
        ("season", "team"),
        "FanGraphs park factors (private research data): one row per season and team.",
        chunk_by="season",
        chunk_prefix="season-",
    ),
    FangraphsFile(
        "park_factors_handedness",
        "fangraphs_park_factors_handedness",
        ("season", "team"),
        "FanGraphs park factors by batter handedness (private research data), from 2002.",
        chunk_by="season",
        chunk_prefix="season-",
    ),
    FangraphsFile(
        "projection",
        "fangraphs_projection",
        (
            "playerid",
            "_projection_system",
            "_stat_group",
            "_horizon",
            "_captured_date",
            "_row_hash",
        ),
        "FanGraphs projection snapshots (private research data): a row per system, player, capture date and change.",
        chunk_by="_captured_date",
        chunk_prefix="capture-",
    ),
    FangraphsFile(
        "prospects",
        "fangraphs_prospects",
        ("season", "playerid", "minormasterid"),
        "FanGraphs prospect board (private research data): scouting grades per player and season.",
        chunk_by="season",
        chunk_prefix="season-",
    ),
    FangraphsFile(
        "split_batting",
        "fangraphs_split_batting",
        ("playerid", "season", "_split", "_scope"),
        "FanGraphs batting split leaderboards (private research data): a curated set of splits per season.",
        chunk_by="season",
        chunk_prefix="season-",
    ),
    FangraphsFile(
        "split_pitching",
        "fangraphs_split_pitching",
        ("playerid", "season", "_split", "_scope"),
        "FanGraphs pitching split leaderboards (private research data): a curated set of splits per season.",
        chunk_by="season",
        chunk_prefix="season-",
    ),
)
BY_DATASET: dict[str, FangraphsFile] = {f.dataset: f for f in FILES}
DATASET_KEYS: dict[str, tuple[str, ...]] = {f.dataset: f.keys for f in FILES}

__all__ = ["BY_DATASET", "DATASET_KEYS", "FILES", "FangraphsFile"]
