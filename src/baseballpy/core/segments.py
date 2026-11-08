"""Processed segments (ADR 95, 96): one Parquet file per dataset per segment, named by a commit line.

A source gives one parsing function, ``normalize(unit_id, responses) -> {dataset: DatasetRows}``; this
module holds no source-specific code. For every unit (one game) the rows of each dataset are handed
to a :class:`ProcessedSegmentFiles`, which writes them with one ``ParquetWriter`` per dataset, one
row group per ``row_group_units`` units, so that no more than that many units of rows are held in
memory. Each row carries ``_raw_sha256``, the sha256 of the response it was made from.

Open files are written as ``processed/<source>/<dataset>/[season=Y/]_open/seg-NNNN.parquet.part``: in
the dataset's own folder (a rename never crosses a disk), ending in ``.part`` and under an
underscore folder, so readers that match ``seg-*.parquet`` or ``*.parquet`` never see them.
Renaming them into place and the commit line belong to task 3.3 (B-362); until then ``commit`` and
``refresh`` of :class:`SegmentWriter` raise ``NotImplementedError``.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import _replace_with_retry
from baseballpy.core.config import LakeConfig
from baseballpy.core.responselog import OPEN_DIRNAME, Response, ResponseLog
from baseballpy.core.stores import PARQUET_COMPRESSION

LINEAGE_COLUMN = "_raw_sha256"
#: units (games) per row group of a processed segment file; memory holds about this many units of rows
ROW_GROUP_UNITS = 50


@dataclass(frozen=True)
class DatasetRows:
    """The rows one dataset got from one response, and that response's sha256."""

    table: pa.Table
    raw_sha256: str


Normalize = Callable[[str, Sequence[Response]], Mapping[str, DatasetRows]]


def segment_file_name(segment: int) -> str:
    """``seg-0001.parquet``: the same name in the raw folder and in every dataset folder."""
    return f"seg-{segment:04d}.parquet"


def _replace(source: Path, target: Path) -> None:
    """Rename an open file into place (the Windows retry of ``core.atomic``); a crash point of the tests."""
    _replace_with_retry(source, target)


def _append_commit_line(path: Path, line: Mapping[str, object]) -> None:
    """Append one JSON line to ``segments.json`` and flush it (task 3.3, B-362); a crash point of the tests."""
    raise NotImplementedError("commit line: task 3.3 (B-362)")


class ProcessedSegmentFiles:
    """The open files of one segment: one ``.part`` Parquet file per dataset that has rows."""

    def __init__(
        self,
        config: LakeConfig,
        source: str,
        season: int | None,
        segment: int,
        row_group_units: int = ROW_GROUP_UNITS,
    ) -> None:
        if row_group_units < 1:
            raise ValueError("row_group_units must be at least 1")
        self._config = config
        self._source = source
        self._season = season
        self._segment = segment
        self._row_group_units = row_group_units
        self._pending: dict[str, list[pa.Table]] = {}
        self._pending_units = 0
        self._writers: dict[str, pq.ParquetWriter] = {}
        self._rows: dict[str, int] = {}

    def final_path(self, dataset: str) -> Path:
        """Where the file of ``dataset`` goes when the segment is committed."""
        folder = self._config.processed_dir(self._source, dataset, self._season)
        return folder / segment_file_name(self._segment)

    def part_path(self, dataset: str) -> Path:
        """The open file of ``dataset``: in ``_open/`` of its folder, ending in ``.part``."""
        final = self.final_path(dataset)
        return final.parent / OPEN_DIRNAME / f"{final.name}.part"

    def add(self, rows: Mapping[str, DatasetRows]) -> None:
        """Take the rows of one unit; write a row group when ``row_group_units`` units are waiting."""
        for dataset, item in rows.items():
            if LINEAGE_COLUMN in item.table.column_names:
                raise ValueError(f"{dataset}: the table already has a {LINEAGE_COLUMN} column")
            if item.table.num_rows == 0:
                continue  # a dataset with no row in the segment gets no file
            lineage = pa.array([item.raw_sha256] * item.table.num_rows, pa.string())
            self._pending.setdefault(dataset, []).append(
                item.table.append_column(LINEAGE_COLUMN, lineage)
            )
        self._pending_units += 1
        if self._pending_units >= self._row_group_units:
            self._flush()

    def _flush(self) -> None:
        """Write what is waiting as one row group per dataset."""
        for dataset, tables in self._pending.items():
            table = pa.concat_tables(tables)  # raises when the schemas of two units differ
            writer = self._writers.get(dataset)
            if writer is None:
                part = self.part_path(dataset)
                part.parent.mkdir(parents=True, exist_ok=True)
                writer = pq.ParquetWriter(part, table.schema, compression=PARQUET_COMPRESSION)
                self._writers[dataset] = writer
            writer.write_table(table, row_group_size=table.num_rows)
            self._rows[dataset] = self._rows.get(dataset, 0) + table.num_rows
        self._pending = {}
        self._pending_units = 0

    def close(self) -> dict[str, int]:
        """Write the last row group, close every file, and return the row count per dataset.

        The files stay as ``.part`` files: the commit renames them (task 3.3).
        """
        self._flush()
        for writer in self._writers.values():
            writer.close()
        self._writers = {}
        for dataset, rows in self._rows.items():
            footer = pq.ParquetFile(self.part_path(dataset)).metadata  # raises on a corrupt footer
            if footer.num_rows != rows:
                raise ValueError(f"{dataset}: footer has {footer.num_rows} rows, wrote {rows}")
        return dict(self._rows)

    def abort(self) -> None:
        """Close and delete every open file (a failed or abandoned segment)."""
        for writer in self._writers.values():
            writer.close()
        for dataset in list(self._writers) + list(self._rows):
            self.part_path(dataset).unlink(missing_ok=True)
        self._writers = {}
        self._rows = {}
        self._pending = {}
        self._pending_units = 0


class SegmentWriter:
    """The response log plus the processed files of one source and season (task 3.2 part).

    ``add_unit`` journals the responses, parses them with ``normalize`` and hands the rows to the open
    files. ``commit`` and ``refresh`` follow in tasks 3.3 and 3.4, the writer lock in task 3.5.
    """

    def __init__(
        self,
        config: LakeConfig,
        source: str,
        season: int | None,
        normalize: Normalize,
        *,
        row_group_units: int = ROW_GROUP_UNITS,
    ) -> None:
        self.log = ResponseLog(config, source, season)
        self._normalize = normalize
        self._files = ProcessedSegmentFiles(
            config, source, season, self.log.next_segment(), row_group_units
        )

    def stored(self) -> frozenset[str]:
        """The ids of the units that are committed or in the journal."""
        return self.log.stored()

    def committed_units(self) -> frozenset[str]:
        """The ids of the units a commit line names."""
        return self.log.committed_units()

    def add_unit(self, unit_id: str, responses: Sequence[Response]) -> None:
        """Journal a finished unit, then parse it and give its rows to the open files."""
        rows = self._normalize(unit_id, responses)  # a parsing error stops before the journal
        self.log.add_unit(unit_id, responses)
        self._files.add(rows)

    def commit(self) -> int | None:
        """Rename the open files into place and append the commit line (task 3.3, B-362)."""
        raise NotImplementedError("processed segment commit: task 3.3 (B-362)")

    def refresh(self, segment: int, units: Mapping[str, Sequence[Response]]) -> None:
        """Rewrite a committed segment under the same file names (task 3.4, B-363)."""
        raise NotImplementedError("segment refresh: task 3.4 (B-363)")
