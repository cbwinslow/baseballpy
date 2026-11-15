"""Live game rows in the lake (ADR 137): one small Parquet file per game, rewritten whole, never appended.

``processed/mlb_api/game_live_events/season=Y/live-<game_pk>.parquet`` holds every pitch and action event of one game
so far, in exactly the schema of ``game_feed_play_events`` (``to_arrow`` runs the historical flattener on the live
play). Each :meth:`LiveGameSink.write` merges the new events into the file's rows (a key seen twice keeps its last row,
so a restart that sends events again never doubles them) and replaces the file atomically (``atomic_write_parquet``:
a ``.part`` file, a footer check, ``os.replace``). A reader therefore sees the old rows or the new rows of a game, never
half, and DuckDB views and ``baseballpy.read`` see them at once. A game is a few hundred rows, so a rewrite is cheap.

The finished game is stored by the normal ingest in ``game_feed_play_events``; these files are never merged into it
(the open-games view of task 4.2 hides a game once it is stored there).
"""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from baseballpy.core.atomic import atomic_write_parquet
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import LIVE_TO_STORED_DATASET, DatasetSpec, get_dataset
from baseballpy.core.listing import dataset_files
from baseballpy.sources import catalog
from baseballpy.sources.mlb_api.stream import LiveEvent, to_arrow

SOURCE = "mlb_api"
DATASET = "game_live_events"
#: file name prefix of a live game; the layout audit and the readers know it (see ``layout_audit``)
FILE_PREFIX = "live-"


def last_row_per_key(table: pa.Table, keys: Sequence[str]) -> pa.Table:
    """``table`` with one row per key (the last one seen), in the order the rows first reached their last place."""
    if table.num_rows == 0:
        return table
    marked = table.append_column("_row", pa.array(range(table.num_rows), pa.int64()))
    last = marked.group_by(list(keys)).aggregate([("_row", "max")])
    rows = pc.sort_indices(last["_row_max"])
    return table.take(pc.take(last["_row_max"], rows))


class LiveGameSink:
    """Writes the live rows of games into the lake, one file per game."""

    def __init__(self, config: LakeConfig) -> None:
        catalog.register_all()
        self.config = config
        self.spec: DatasetSpec = get_dataset(SOURCE, DATASET)

    def path(self, season: int, game_pk: int) -> Path:
        """The file of a game (not created here)."""
        return (
            self.config.processed_dir(SOURCE, DATASET, season) / f"{FILE_PREFIX}{game_pk}.parquet"
        )

    def stored_games(self, season: int) -> set[int]:
        """The games of a season that the normal ingest has stored (their ``game_pk`` in the long-term dataset)."""
        source, name = LIVE_TO_STORED_DATASET[self.spec.key].split(".")
        folder = self.config.processed_dir(source, name, season)
        games: set[int] = set()
        for file in dataset_files(folder, by_season=False):
            column = pc.unique(pq.read_table(file, columns=["game_pk"])["game_pk"])
            games.update(int(pk) for pk in column.drop_null().to_pylist())
        return games

    def prune(self, season: int, older_than_days: int, now: datetime) -> list[int]:
        """Delete the live files of games that are stored in the long-term dataset and older than the limit.

        Housekeeping only: the open-games view already hides stored games, so no count changes. Returns the game_pks.
        """
        folder = self.config.processed_dir(SOURCE, DATASET, season)
        if not folder.is_dir():
            return []
        stored = self.stored_games(season)
        if not stored:
            return []
        cutoff = now.timestamp() - older_than_days * 86400
        removed: list[int] = []
        for path in sorted(folder.glob(f"{FILE_PREFIX}*.parquet")):
            game_pk = int(path.stem.removeprefix(FILE_PREFIX))
            if game_pk in stored and path.stat().st_mtime < cutoff:
                path.unlink()
                removed.append(game_pk)
        return removed

    def write(self, season: int, game_pk: int, events: Sequence[LiveEvent]) -> int:
        """Merge ``events`` into the game's file and return the rows the file now holds.

        Pitch and action events become rows; ``play_result`` and ``game_status`` events have none in this schema.
        """
        path = self.path(season, game_pk)
        new = to_arrow(list(events))
        existing = (
            pq.read_table(path, schema=self.spec.schema)
            if path.exists()
            else self.spec.schema.empty_table()
        )
        if new.num_rows == 0:
            return int(existing.num_rows)  # nothing to add: no file is created or rewritten
        merged = last_row_per_key(
            pa.concat_tables([existing, new.cast(self.spec.schema)]), self.spec.keys
        )
        atomic_write_parquet(merged, path, compression="zstd")
        return int(merged.num_rows)
