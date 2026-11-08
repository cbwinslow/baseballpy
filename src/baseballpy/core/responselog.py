"""The response log (ADR 95): every HTTP response is kept once, a crash loses no finished unit.

A *unit* is one piece of work that is stored or not stored as a whole (one game: its feed, its
boxscore, ...). Each finished unit is appended to a journal file, ``raw/<source>/[season=Y/]_open/
journal.zst``, and flushed to disk before ``add_unit`` returns. After a crash or restart the journal
is read again and the units in it are not fetched a second time.

One journal record is one unit, so a unit is whole or missing, never half:

    header   ">III": compressed size, original size, crc32 of the compressed bytes
    body     one zstd frame (``pyarrow.Codec``) of the packed unit: its id and its responses

A record that is cut short (power cut in the middle of a write) or does not match its crc ends the
replay: every record before it is kept, it and everything after it is dropped, and the file is cut
back to the last good record so that new records follow whole ones.

``commit`` writes the open units as one raw segment, ``seg-NNNN.parquet`` (one row per response:
url, fetched_at, status, etag, sha256 of the original bytes, the bytes), then appends one JSON line
to ``segments.json``; only then are the units counted as stored and the journal deleted. A segment
file that no line names (a crash between the rename and the line) is deleted on the next start and
its units come back from the journal.
"""

import hashlib
import json
import os
import struct
import zlib
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import atomic_write
from baseballpy.core.config import LakeConfig
from baseballpy.core.stores import schema_fingerprint

JOURNAL_NAME = "journal.zst"
OPEN_DIRNAME = "_open"
COMMIT_NAME = "segments.json"
#: zstd level 9 is the knee measured in task 2.4 (28 MB for 250 games; level 19 is 20% smaller but 27 times
#: slower). Page and row-group sizes made no difference at these body sizes. What does matter is the row
#: order: the responses of one game stay next to each other, so zstd finds what they repeat.
RAW_LEVEL = 9
RAW_PAGE_BYTES = 8 * 1024 * 1024
RAW_ROW_GROUP_ROWS = 500
RAW_SCHEMA = pa.schema(
    [
        ("url", pa.string()),
        ("fetched_at", pa.string()),
        ("status", pa.int32()),
        ("etag", pa.string()),
        ("sha256", pa.string()),
        ("body", pa.large_binary()),
        ("legacy_path", pa.string()),
    ]
)
#: zstd level of a journal record: the journal is short-lived, so speed matters more than size
JOURNAL_LEVEL = 3

_HEADER = struct.Struct(">III")
_U16 = struct.Struct(">H")
_U32 = struct.Struct(">I")


@dataclass(frozen=True)
class Response:
    """One HTTP response: the original bytes, and what is needed to say where they came from."""

    url: str
    body: bytes
    fetched_at: str
    status: int = 200
    etag: str = ""

    @property
    def sha256(self) -> str:
        """The sha256 of the original bytes (the identity of the response)."""
        return hashlib.sha256(self.body).hexdigest()


class _Cursor:
    """Reads the packed fields of a record; a short or odd record raises ``ValueError``."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._at = 0

    def take(self, size: int) -> bytes:
        end = self._at + size
        if end > len(self._data):
            raise ValueError("record is shorter than its fields say")
        chunk = self._data[self._at : end]
        self._at = end
        return chunk

    def u16(self) -> int:
        return int(_U16.unpack(self.take(_U16.size))[0])

    def u32(self) -> int:
        return int(_U32.unpack(self.take(_U32.size))[0])

    def text(self) -> str:
        return self.take(self.u32()).decode("utf-8")

    def done(self) -> bool:
        return self._at == len(self._data)


def _pack_text(value: str) -> bytes:
    raw = value.encode("utf-8")
    return _U32.pack(len(raw)) + raw


def pack_unit(unit_id: str, responses: Sequence[Response]) -> bytes:
    """The bytes of one journal record before compression."""
    parts = [_pack_text(unit_id), _U32.pack(len(responses))]
    for response in responses:
        parts += [
            _pack_text(response.url),
            _pack_text(response.fetched_at),
            _U16.pack(response.status),
            _pack_text(response.etag),
            _U32.pack(len(response.body)),
            response.body,
        ]
    return b"".join(parts)


def unpack_unit(data: bytes) -> tuple[str, list[Response]]:
    """The unit id and responses of a record; ``ValueError`` when the record is not whole."""
    cursor = _Cursor(data)
    unit_id = cursor.text()
    responses = []
    for _ in range(cursor.u32()):
        url = cursor.text()
        fetched_at = cursor.text()
        status = cursor.u16()
        etag = cursor.text()
        body = cursor.take(cursor.u32())
        responses.append(Response(url, body, fetched_at, status, etag))
    if not cursor.done():
        raise ValueError("record has bytes after its last response")
    return unit_id, responses


def _codec() -> pa.Codec:
    return pa.Codec("zstd", compression_level=JOURNAL_LEVEL)


def encode_record(unit_id: str, responses: Sequence[Response]) -> bytes:
    """One whole journal record: header plus the compressed unit."""
    packed = pack_unit(unit_id, responses)
    compressed: bytes = _codec().compress(packed, asbytes=True)
    return _HEADER.pack(len(compressed), len(packed), zlib.crc32(compressed)) + compressed


def read_journal(path: Path) -> tuple[dict[str, list[Response]], int]:
    """The units of a journal and the size in bytes of its whole records.

    Reading stops at the first record that is cut short, does not match its crc or cannot be
    unpacked; a unit written twice keeps its last version.
    """
    units: dict[str, list[Response]] = {}
    if not path.exists():
        return units, 0
    data = path.read_bytes()
    at = 0
    while at + _HEADER.size <= len(data):
        compressed_size, packed_size, crc = _HEADER.unpack_from(data, at)
        start = at + _HEADER.size
        end = start + compressed_size
        if end > len(data) or zlib.crc32(data[start:end]) != crc:
            break
        try:
            packed = _codec().decompress(
                data[start:end], decompressed_size=packed_size, asbytes=True
            )
            unit_id, responses = unpack_unit(packed)
        except (ValueError, pa.ArrowException):
            break
        units[unit_id] = responses
        at = end
    return units, at


class RawSegmentSink:
    """Writes a raw segment table as one atomic Parquet file (``SinkProtocol``).

    The file is written beside its target as ``<name>.<id>.part`` (readers only match ``*.parquet``),
    its footer is checked, then it is renamed into place with the Windows retry of ``core.atomic``.
    """

    def write(self, table: pa.Table, destination: str, **kwargs: Any) -> int:
        """Write ``table`` to ``destination``; returns the number of rows."""
        with atomic_write(Path(destination)) as part:
            pq.write_table(
                table,
                part,
                compression="zstd",
                compression_level=int(kwargs.get("level", RAW_LEVEL)),
                data_page_size=int(kwargs.get("page_bytes", RAW_PAGE_BYTES)),
                row_group_size=int(kwargs.get("row_group_rows", RAW_ROW_GROUP_ROWS)),
                use_dictionary=False,
            )
            rows = pq.ParquetFile(part).metadata.num_rows  # raises if the footer is corrupt
            if rows != table.num_rows:
                raise ValueError(f"parquet footer row count {rows} != table rows {table.num_rows}")
        return int(table.num_rows)

    def write_stream(self, reader: pa.RecordBatchReader, destination: str, **kwargs: Any) -> int:
        """Write the batches of ``reader`` as one segment file; returns the number of rows."""
        return self.write(reader.read_all(), destination, **kwargs)


def _segment_name(segment: int) -> str:
    return f"seg-{segment:04d}.parquet"


def file_sha256(path: Path) -> str:
    """The sha256 of a file, read in blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def append_commit_line(path: Path, line: Mapping[str, object]) -> None:
    """Append one JSON line to ``segments.json`` and flush it to disk; this is the moment a segment counts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(json.dumps(line, separators=(",", ":")).encode("utf-8") + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_commit_lines(path: Path) -> tuple[list[dict[str, Any]], int]:
    """The lines of ``segments.json`` and the size in bytes of its whole lines.

    A last line that is cut short (no newline, or not JSON) is ignored; a bad line before the last
    one raises ``ValueError``, because the file is then damaged and not merely torn.
    """
    if not path.exists():
        return [], 0
    data = path.read_bytes()
    lines: list[dict[str, Any]] = []
    good = 0
    for raw in data.splitlines(keepends=True):
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            good += len(raw)
            continue
        try:
            if not raw.endswith(b"\n"):
                raise ValueError("no end of line")
            lines.append(json.loads(text))
        except ValueError:
            if good + len(raw) == len(data):
                break
            raise
        good += len(raw)
    return lines, good


class ResponseLog:
    """The log of one source and season (``season=None`` for a source that is not split by season)."""

    def __init__(self, config: LakeConfig, source: str, season: int | None = None) -> None:
        self.config = config
        self.source = source
        self.season = season
        self._units: dict[str, list[Response]] = {}
        self._committed: dict[str, str] = {}
        self._lines: list[dict[str, Any]] = []
        self._replay()

    @property
    def season_dir(self) -> Path:
        """``raw/<source>/[season=Y/]``; never created by asking for it."""
        base = self.config.raw_root / self.source
        return base if self.season is None else base / f"season={self.season}"

    @property
    def journal_path(self) -> Path:
        """The crash journal of the open segment."""
        return self.season_dir / OPEN_DIRNAME / JOURNAL_NAME

    @property
    def commit_path(self) -> Path:
        """``segments.json``: one line per committed segment."""
        return self.season_dir / COMMIT_NAME

    def _replay(self) -> None:
        """Start-up: read the commit lines, drop what no line names, replay the journal."""
        lines, good = read_commit_lines(self.commit_path)
        if self.commit_path.exists() and self.commit_path.stat().st_size != good:
            with self.commit_path.open("r+b") as handle:
                handle.truncate(good)
        self._lines = lines
        named = {name for line in lines for name in line.get("files", {})}
        for unit in (u for line in lines for u in line.get("units", [])):
            self._committed[unit] = ""
        if self.season_dir.is_dir():
            for leftover in (
                *self.season_dir.glob("*.part"),
                *self.season_dir.glob("seg-*.parquet"),
            ):
                if leftover.name not in named:
                    with suppress(OSError):
                        leftover.unlink()
        units, good = read_journal(self.journal_path)
        # a crash after the commit line but before the journal was deleted leaves units a line already names
        self._units = {u: r for u, r in units.items() if u not in self._committed}
        if len(self._units) != len(units):
            if self._units:
                self._rewrite_journal()
            else:
                self.journal_path.unlink(missing_ok=True)
        elif self.journal_path.exists() and self.journal_path.stat().st_size != good:
            with self.journal_path.open("r+b") as handle:
                handle.truncate(good)
                handle.flush()
                os.fsync(handle.fileno())

    def _rewrite_journal(self) -> None:
        """Write the open units to a fresh journal (atomic: the old one is replaced whole)."""
        with atomic_write(self.journal_path) as part:
            part.write_bytes(b"".join(encode_record(u, r) for u, r in self._units.items()))

    def open_units(self) -> dict[str, list[Response]]:
        """The units that are journalled and not yet committed (a copy)."""
        return dict(self._units)

    def stored(self) -> frozenset[str]:
        """The ids of the units that are committed or in the journal."""
        return frozenset(self._units) | frozenset(self._committed)

    def committed_units(self) -> frozenset[str]:
        """The ids of the units a commit line names."""
        return frozenset(self._committed)

    def next_segment(self) -> int:
        """The number of the next segment: one after the last commit line."""
        return 1 + max((int(line["segment"]) for line in self._lines), default=0)

    def add_unit(self, unit_id: str, responses: Sequence[Response]) -> None:
        """Append a finished unit to the journal; it is on disk when this returns."""
        record = encode_record(unit_id, responses)
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        with self.journal_path.open("ab") as handle:
            handle.write(record)
            handle.flush()
            os.fsync(handle.fileno())
        self._units[unit_id] = list(responses)

    def commit(self) -> int | None:
        """Write the open units as one raw segment and its commit line; returns the segment number.

        Order matters: the segment file is renamed into place first, the line is appended second, the
        journal is deleted last. A crash anywhere leaves either nothing counted (the journal replays)
        or everything counted (a leftover journal holds only units a line already names).
        """
        line = self.stage_raw()
        if line is None:
            return None
        append_commit_line(self.commit_path, line)
        self.finish_commit(line)
        return int(line["segment"])

    def stage_raw(self) -> dict[str, Any] | None:
        """Write the open units as the raw segment file, in place, and return its commit line.

        The line is not written: the caller adds what else belongs to the segment (the processed
        files) and then calls :func:`append_commit_line` and :meth:`finish_commit`. ``None`` when no
        unit is open.
        """
        if not self._units:
            return None
        segment = self.next_segment()
        name = _segment_name(segment)
        path = self.season_dir / name
        table = self._table()
        RawSegmentSink().write(table, str(path))
        return {
            "segment": segment,
            "units": sorted(self._units),
            "raw": name,
            "files": {name: {"sha256": file_sha256(path), "rows": table.num_rows}},
            "schema_sha256": {"raw": schema_fingerprint(RAW_SCHEMA)},
            "committed_at": datetime.now(UTC).isoformat(),
        }

    def finish_commit(self, line: dict[str, Any]) -> None:
        """After the line is on disk: count the units as stored and delete the journal."""
        self._lines.append(line)
        for unit in line["units"]:
            self._committed[unit] = str(line["raw"])
        self._units = {}
        with suppress(FileNotFoundError):
            self.journal_path.unlink()
        with suppress(OSError):
            self.journal_path.parent.rmdir()

    @property
    def lines(self) -> list[dict[str, Any]]:
        """The commit lines read so far (a copy)."""
        return list(self._lines)

    def _table(self) -> pa.Table:
        """One row per response of every open unit."""
        rows = [response for unit in self._units.values() for response in unit]
        return pa.table(
            {
                "url": [r.url for r in rows],
                "fetched_at": [r.fetched_at for r in rows],
                "status": [r.status for r in rows],
                "etag": [r.etag for r in rows],
                "sha256": [r.sha256 for r in rows],
                "body": [r.body for r in rows],
                "legacy_path": [None] * len(rows),
            },
            schema=RAW_SCHEMA,
        )

    def read(self, sha256: str) -> bytes:
        """The original bytes of a stored response, from the open units or a committed segment."""
        for unit in self._units.values():
            for response in unit:
                if response.sha256 == sha256:
                    return response.body
        for line in self._lines:
            table = pq.read_table(
                self.season_dir / line["raw"],
                columns=["sha256", "body"],
                filters=[("sha256", "=", sha256)],
            )
            if table.num_rows:
                return bytes(table.column("body")[0].as_py())
        raise KeyError(sha256)
