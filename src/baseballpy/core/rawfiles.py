"""Compressed raw files: ``name.json`` is stored as ``name.json.gz`` with the checksum of the original.

The manifest keeps the logical name (``name.json``), the original byte count and the sha256 of the
original bytes, plus ``stored: "gzip"``; readers ask :class:`~baseballpy.core.stores.RawStore` and
never need to know which form is on disk.
"""

import gzip
import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

GZIP = "gzip"
GZIP_SUFFIX = ".gz"
#: text formats that shrink well; anything else (zip, parquet, ...) is stored as it came
COMPRESSIBLE_SUFFIXES = frozenset({".json", ".csv", ".jsonl", ".txt", ".xml", ".html", ".tsv"})
_BLOCK = 1 << 20


def is_compressible(name: str) -> bool:
    """True for a text file that is not already compressed."""
    lowered = name.lower()
    return not lowered.endswith(GZIP_SUFFIX) and Path(lowered).suffix in COMPRESSIBLE_SUFFIXES


def gzip_bytes(data: bytes) -> bytes:
    """Gzip without a timestamp, so the same bytes always give the same file."""
    return gzip.compress(data, compresslevel=6, mtime=0)


def stored_path(directory: Path, name: str) -> Path | None:
    """The file that holds ``name`` (plain or ``.gz``), or ``None`` when neither exists."""
    plain = directory / name
    if plain.exists():
        return plain
    packed = directory / (name + GZIP_SUFFIX)
    return packed if packed.exists() else None


def _was_packed(path: Path, name: str) -> bool:
    """True when ``path`` is the gzipped form of ``name`` (a name that already ends in ``.gz``
    is a file the provider or the caller compressed: its bytes are kept as they are)."""
    return path.name == name + GZIP_SUFFIX


def read_logical(path: Path, name: str) -> bytes:
    """The original bytes of the stored file for ``name``, whichever form it is in."""
    data = path.read_bytes()
    return gzip.decompress(data) if _was_packed(path, name) else data


def logical_sha256(path: Path, name: str) -> str:
    """sha256 of the original bytes, streaming (a packed file is decompressed on the fly)."""
    digest = hashlib.sha256()
    opener = gzip.open if _was_packed(path, name) else open
    with opener(path, "rb") as handle:
        for block in iter(lambda: handle.read(_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def is_packed(entry: Mapping[str, Any] | None) -> bool:
    """True when a manifest entry says its file is stored gzipped."""
    return bool(entry and entry.get("stored") == GZIP)
