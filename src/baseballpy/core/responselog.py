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

``commit`` (the raw segment, ``seg-NNNN.parquet``, and its line in ``segments.json``) and ``read``
belong to task 2.3 (B-358) and raise ``NotImplementedError`` until then.
"""

import hashlib
import os
import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa

from baseballpy.core.config import LakeConfig

JOURNAL_NAME = "journal.zst"
OPEN_DIRNAME = "_open"
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


class ResponseLog:
    """The log of one source and season (``season=None`` for a source that is not split by season)."""

    def __init__(self, config: LakeConfig, source: str, season: int | None = None) -> None:
        self.config = config
        self.source = source
        self.season = season
        self._units: dict[str, list[Response]] = {}
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

    def _replay(self) -> None:
        """Load the units of the journal and cut a torn tail off the file."""
        units, good = read_journal(self.journal_path)
        self._units = units
        if self.journal_path.exists() and self.journal_path.stat().st_size != good:
            with self.journal_path.open("r+b") as handle:
                handle.truncate(good)
                handle.flush()
                os.fsync(handle.fileno())

    def stored(self) -> frozenset[str]:
        """The ids of the units that are in the journal (committed units are added by task 2.3)."""
        return frozenset(self._units)

    def add_unit(self, unit_id: str, responses: Sequence[Response]) -> None:
        """Append a finished unit to the journal; it is on disk when this returns."""
        record = encode_record(unit_id, responses)
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        with self.journal_path.open("ab") as handle:
            handle.write(record)
            handle.flush()
            os.fsync(handle.fileno())
        self._units[unit_id] = list(responses)

    def commit(self) -> None:
        """Write the open units as a raw segment and its commit line (task 2.3, B-358)."""
        raise NotImplementedError("raw segment writer: task 2.3 (B-358)")

    def read(self, sha256: str) -> bytes:
        """The original bytes of a stored response (task 2.3, B-358)."""
        raise NotImplementedError("raw segment reader: task 2.3 (B-358)")
