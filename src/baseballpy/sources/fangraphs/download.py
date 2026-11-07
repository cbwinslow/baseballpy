"""FanGraphs downloads into the same typed tables as the files you supply.

A leaderboard season is one chunk (``season-YYYY``); a past season is not fetched again unless
asked. A projection run keeps only the rows whose values changed since the player's last stored
snapshot (the md5 of the row's values), so a daily run adds only what moved. Both write the chunk
names the inbox import uses, so a season or a day that arrives both ways is stored once.
"""

import logging
from dataclasses import dataclass, field
from datetime import date

import pyarrow as pa

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.rawlog import RawLog
from baseballpy.core.stores import ProcessedStore
from baseballpy.sources import catalog
from baseballpy.sources.fangraphs.extractor import FangraphsWeb
from baseballpy.sources.fangraphs.files import BY_DATASET
from baseballpy.sources.fangraphs.normalizer import FangraphsNormalizer
from baseballpy.sources.fangraphs.records import now_stamp, projection_hash, shape_row
from baseballpy.sources.fangraphs.web import LEADERBOARDS, ROS_SYSTEMS, current_season

logger = logging.getLogger(__name__)

DOWNLOADABLE = (*LEADERBOARDS, "projection")


@dataclass
class DownloadOutcome:
    """What one download job did."""

    rows: dict[str, int] = field(default_factory=dict)
    cached: bool = False
    detail: str = ""


def download_season(
    dataset: str,
    season: int,
    *,
    config: LakeConfig,
    web: FangraphsWeb,
    normalizer: FangraphsNormalizer,
    force: bool = False,
    today: date | None = None,
) -> DownloadOutcome:
    """Download one season of a leaderboard (batting, pitching or fielding) as chunk ``season-Y``."""
    if dataset not in LEADERBOARDS:
        raise ValueError(f"no leaderboard download for {dataset!r}; known: {sorted(LEADERBOARDS)}")
    catalog.register_all()
    spec = get_dataset("fangraphs", dataset)
    store = ProcessedStore(config)
    chunk = f"{BY_DATASET[dataset].chunk_prefix}{season}"
    if not force and season < current_season(today) and store.is_cached(spec, chunk):
        return DownloadOutcome(rows={dataset: 0}, cached=True, detail=f"{season} already stored")
    raw = RawLog()
    rows = web.leaderboard(LEADERBOARDS[dataset], season, raw)
    stamp = now_stamp()
    shaped = [shape_row(r, {"_season": str(season), "_loaded_at": stamp}) for r in rows]
    table = normalizer.normalize_records(dataset, shaped)
    if config.enabled:
        web.keep(dataset, f"leaders-{season}.jsonl.gz", raw)
        store.put(spec, table, chunk_id=chunk, metadata={"season": season})
    return DownloadOutcome(
        rows={dataset: table.num_rows}, detail=f"{season}: {table.num_rows} rows"
    )


def _known_hashes(store: ProcessedStore, system: str, group: str) -> dict[str, str]:
    """The newest stored ``_row_hash`` per player for one projection system and stat group."""
    spec = get_dataset("fangraphs", "projection")
    table = store.read(
        spec,
        columns=["playerid", "_projection_system", "_stat_group", "_row_hash", "_captured_date"],
    )
    newest: dict[str, tuple[date, str]] = {}
    for r in table.to_pylist():
        if r["_projection_system"] != system or r["_stat_group"] != group or r["playerid"] is None:
            continue
        stamp = r["_captured_date"] or date.min
        if r["playerid"] not in newest or stamp >= newest[r["playerid"]][0]:
            newest[r["playerid"]] = (stamp, r["_row_hash"])
    return {player: value[1] for player, value in newest.items()}


def download_projection(
    system: str,
    group: str,
    *,
    config: LakeConfig,
    web: FangraphsWeb,
    normalizer: FangraphsNormalizer,
    today: date | None = None,
) -> DownloadOutcome:
    """Download one projection system's board and store the rows that changed since last time."""
    catalog.register_all()
    spec = get_dataset("fangraphs", "projection")
    store = ProcessedStore(config)
    captured = (today or date.today()).isoformat()
    horizon = "ros" if system in ROS_SYSTEMS else "preseason"
    raw = RawLog()
    fetched = web.projections(system, group, raw)
    known = _known_hashes(store, system, group)
    stamp = now_stamp()
    changed: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in fetched:
        player = row.get("playerid")
        if player is None or str(player) == "" or str(player) in seen:
            continue  # no id: its history cannot be followed; one row per player and system
        seen.add(str(player))
        digest = projection_hash(row)
        if known.get(str(player)) == digest:
            continue
        changed.append(
            shape_row(
                row,
                {
                    "_projection_system": system,
                    "_stat_group": group,
                    "_horizon": horizon,
                    "_captured_date": captured,
                    "_row_hash": digest,
                    "_loaded_at": stamp,
                },
            )
        )
    table: pa.Table = normalizer.normalize_records("projection", changed)
    if config.enabled:
        web.keep("projection", f"projections-{system}-{group}-{captured}.jsonl.gz", raw)
        if table.num_rows:
            chunk = f"{BY_DATASET['projection'].chunk_prefix}{captured}-{system}-{group}"
            store.put(spec, table, chunk_id=chunk, metadata={"system": system, "group": group})
    return DownloadOutcome(
        rows={"projection": table.num_rows},
        detail=f"{system}/{group}: {len(fetched)} players, {table.num_rows} changed",
    )


__all__ = ["DOWNLOADABLE", "DownloadOutcome", "download_projection", "download_season"]
