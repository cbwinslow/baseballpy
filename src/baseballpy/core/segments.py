"""Processed segments (ADR 95, 96): one Parquet file per dataset per segment, named by a commit line.

A source gives one parsing function, ``normalize(unit_id, responses) -> {dataset: DatasetRows}``; this
module holds no source-specific code. For every unit (one game) the rows of each dataset are handed
to a :class:`ProcessedSegmentFiles`, which writes them with one ``ParquetWriter`` per dataset, one
row group per ``row_group_units`` units, so that no more than that many units of rows are held in
memory. Each row carries ``_raw_sha256``, the sha256 of the response it was made from.

Open files are written as ``processed/<source>/<dataset>/[season=Y/]_open/seg-NNNN.parquet.part``: in
the dataset's own folder (a rename never crosses a disk), ending in ``.part`` and under an
underscore folder, so readers that match ``seg-*.parquet`` or ``*.parquet`` never see them.
``SegmentWriter.commit`` closes the files, renames the raw segment and every dataset file into place,
and only then appends the commit line (the line is the commit). On start, :class:`SegmentWriter`
deletes every ``seg-*.parquet`` and ``.part`` file that no line names, replays the journal through
``normalize`` and carries on.

``refresh`` rewrites a committed segment under the same file names: the new responses are first
written to ``_open/refresh-NNNN.zst``; the new files are built beside the old ones, each is renamed
over the old file of the same name (a reader sees the old or the new rows of that file, never both),
and a second line for the segment is appended. A refresh that stops half way is run again on start
from its journal; the raw file keeps every old row and adds the new responses (design 5b).
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import _replace_with_retry, atomic_write
from baseballpy.core.config import LakeConfig
from baseballpy.core.responselog import (
    OPEN_DIRNAME,
    Response,
    ResponseLog,
    append_commit_line,
    encode_record,
    file_sha256,
    read_journal,
)
from baseballpy.core.stores import PARQUET_COMPRESSION, schema_fingerprint

LINEAGE_COLUMN = "_raw_sha256"
REFRESH_PREFIX = "refresh-"
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
    """Append the commit line (the moment the segment counts); a crash point of the tests."""
    append_commit_line(path, line)


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
        self._seen: set[str] = set()

    @property
    def segment(self) -> int:
        """The number of the segment these files belong to."""
        return self._segment

    def datasets(self) -> frozenset[str]:
        """Every dataset that was given rows, including those that had none (they get no file)."""
        return frozenset(self._seen)

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
            self._seen.add(dataset)
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
    """The response log plus the processed files of one source and season.

    ``add_unit`` journals the responses, parses them with ``normalize`` and hands the rows to the open
    files; ``commit`` makes the segment count. The writer lock is added in task 3.5, ``refresh`` in 3.4.
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
        self.config = config
        self.source = source
        self.season = season
        self._row_group_units = row_group_units
        self._normalize = normalize
        self.log = ResponseLog(config, source, season)
        self._delete_unnamed_files()
        self._finish_refreshes()
        self._files = self._new_files()
        for unit_id, responses in self.log.open_units().items():  # the journal, parsed again
            self._files.add(self._normalize(unit_id, responses))

    def _new_files(self) -> ProcessedSegmentFiles:
        return ProcessedSegmentFiles(
            self.config, self.source, self.season, self.log.next_segment(), self._row_group_units
        )

    def _dataset_folders(self) -> list[Path]:
        """The season folder of every dataset of this source that exists on disk."""
        base = self.config.processed_root / self.source
        if not base.is_dir():
            return []
        folders = [
            d if self.season is None else d / f"season={self.season}" for d in base.iterdir()
        ]
        return [folder for folder in folders if folder.is_dir()]

    def _delete_unnamed_files(self) -> None:
        """Start-up: delete every segment file and ``.part`` file that no commit line names."""
        named = {
            (dataset, info["file"])
            for line in self.log.latest_lines().values()
            for dataset, info in line.get("datasets", {}).items()
        }
        for folder in self._dataset_folders():
            dataset = folder.parent.name if self.season is not None else folder.name
            for path in folder.glob("seg-*.parquet"):
                if (dataset, path.name) not in named:
                    path.unlink(missing_ok=True)
            for path in (folder / OPEN_DIRNAME).glob("*.part"):
                path.unlink(missing_ok=True)

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
        """Close the segment: rename every file into place, then append the commit line.

        Returns the segment number, or ``None`` when no unit is open. A crash before the line leaves
        files no line names; the next start deletes them and replays the journal.
        """
        files = self._files
        if not self.log.open_units():
            return None
        counts = files.close()
        line = self.log.stage_raw()
        if line is None:  # pragma: no cover - open_units() was not empty
            return None
        datasets: dict[str, dict[str, object]] = {}
        for dataset in sorted(files.datasets()):
            if dataset not in counts:
                datasets[dataset] = {"file": None, "rows": 0}
                continue
            part, final = files.part_path(dataset), files.final_path(dataset)
            digest = file_sha256(part)
            schema = schema_fingerprint(pq.read_schema(part))
            _replace(part, final)
            datasets[dataset] = {
                "file": final.name,
                "rows": counts[dataset],
                "sha256": digest,
                "schema_sha256": schema,
            }
        line["datasets"] = datasets
        _append_commit_line(self.log.commit_path, line)
        self.log.finish_commit(line)
        self._files = self._new_files()
        return int(line["segment"])

    def _refresh_journal(self, segment: int) -> Path:
        return self.log.season_dir / OPEN_DIRNAME / f"{REFRESH_PREFIX}{segment:04d}.zst"

    def refresh(self, segment: int, units: Mapping[str, Sequence[Response]]) -> None:
        """Rewrite a committed segment under the same file names, from the new responses of its units.

        ``units`` must name exactly the units of the segment. The new responses are journalled first, so
        a refresh that stops half way is finished by the next start.
        """
        old = self.log.latest_lines().get(segment)
        if old is None:
            raise ValueError(f"segment {segment} is not committed")
        if set(units) != set(old["units"]):
            raise ValueError(f"a refresh of segment {segment} must name exactly its units")
        journal = self._refresh_journal(segment)
        with atomic_write(journal) as part:
            part.write_bytes(b"".join(encode_record(u, list(r)) for u, r in units.items()))
        self._apply_refresh(segment, units, file_sha256(journal))

    def _finish_refreshes(self) -> None:
        """Start-up: run again every refresh whose journal is still there."""
        folder = self.log.season_dir / OPEN_DIRNAME
        for journal in sorted(folder.glob(f"{REFRESH_PREFIX}*.zst")):
            segment = int(journal.stem.removeprefix(REFRESH_PREFIX))
            line = self.log.latest_lines().get(segment)
            refresh_id = file_sha256(journal)
            if line is not None and line.get("refresh_id") != refresh_id:
                units, _ = read_journal(journal)
                self._apply_refresh(segment, units, refresh_id)
            journal.unlink(missing_ok=True)  # its line is already on disk, or the segment is gone

    def _apply_refresh(
        self, segment: int, units: Mapping[str, Sequence[Response]], refresh_id: str
    ) -> None:
        """Build the new files, rename each over its old one, append the new line, delete the journal."""
        old = self.log.latest_lines()[segment]
        files = ProcessedSegmentFiles(
            self.config, self.source, self.season, segment, self._row_group_units
        )
        for unit_id, responses in units.items():
            files.add(self._normalize(unit_id, responses))
        counts = files.close()
        raw_part, line = self.log.stage_raw_refresh(old, units)
        datasets: dict[str, dict[str, object]] = {}
        for dataset in sorted(files.datasets()):
            if dataset not in counts:
                datasets[dataset] = {"file": None, "rows": 0}
                continue
            part, final = files.part_path(dataset), files.final_path(dataset)
            datasets[dataset] = {
                "file": final.name,
                "rows": counts[dataset],
                "sha256": file_sha256(part),
                "schema_sha256": schema_fingerprint(pq.read_schema(part)),
            }
            _replace(part, final)
        for dataset, info in old.get("datasets", {}).items():
            if info.get("file") and datasets.get(dataset, {}).get("file") is None:
                files.final_path(dataset).unlink(missing_ok=True)  # the refresh has no row for it
                datasets.setdefault(dataset, {"file": None, "rows": 0})
        _replace(raw_part, self.log.season_dir / str(line["raw"]))
        line["datasets"] = datasets
        line["refresh_id"] = refresh_id
        _append_commit_line(self.log.commit_path, line)
        self.log.record_refresh(line)
        self._refresh_journal(segment).unlink(missing_ok=True)
