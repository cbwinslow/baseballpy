"""JSON raw answers for the round-trip check: flattened records as text tables, and the raw response log.

A source that keeps JSON answers flattens them with its own ingest code (never a second copy of it) and hands the
records to :func:`records_table`. Each scalar becomes the text the provider sent, so the generic comparison of
:mod:`baseballpy.core.roundtrip` can check it against the stored cell:

* a JSON string stays as written (``"1.000"`` stays ``"1.000"``, ``"007"`` stays ``"007"``);
* an integer is its decimal text, a float the shortest text that reads back as the same 64-bit float (so a value
  stored as a 32-bit float, or rounded, differs);
* ``true``/``false`` for booleans; ``null`` and the empty string are no value (the loaders store both as NULL).

Answers kept in the response log (ADR 95: ``raw/<source>/season=Y/seg-NNNN.parquet`` named by ``segments.json``)
are read here without the log's writer, which would tidy files on start: the check stays read-only.
"""

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import LINEAGE_COLUMN, DatasetSpec
from baseballpy.core.responselog import COMMIT_NAME, Response, read_commit_lines

JsonScalar = str | int | float | bool | None


def scalar_text(value: JsonScalar) -> str | None:
    """The text of one JSON scalar as the provider sent it (``None`` for no value)."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        # repr is the shortest text that reads back as the same 64-bit float; nan and inf have no JSON form
        return repr(value) if math.isfinite(value) else json.dumps(value)
    return str(value)


def records_table(records: Sequence[Mapping[str, JsonScalar]]) -> pa.Table:
    """Flattened records as one table of text columns, one column per key any record has (first-seen order)."""
    names = list(dict.fromkeys(key for record in records for key in record))
    return pa.table(
        {
            name: pa.array([scalar_text(record.get(name)) for record in records], pa.string())
            for name in names
        }
    )


@dataclass(frozen=True)
class SegmentUnit:
    """One unit (a game) of a committed raw segment."""

    season: int
    raw_file: str
    unit: str


def _season_dirs(config: LakeConfig, source: str, season: int | None) -> list[tuple[int, Path]]:
    base = config.raw_root / source
    if not base.is_dir():
        return []
    out = []
    for child in sorted(base.iterdir()):
        name = child.name
        if not (child.is_dir() and name.startswith("season=") and name[7:].isdigit()):
            continue
        if season is None or int(name[7:]) == season:
            out.append((int(name[7:]), child))
    return out


def segment_units(config: LakeConfig, source: str, season: int | None = None) -> list[SegmentUnit]:
    """Every unit a commit line of the source's response log names (the newest line of each segment wins)."""
    out: list[SegmentUnit] = []
    for folder_season, folder in _season_dirs(config, source, season):
        lines, _ = read_commit_lines(folder / COMMIT_NAME)
        latest = {int(line["segment"]): line for line in lines}
        for _, line in sorted(latest.items()):
            out += [SegmentUnit(folder_season, str(line["raw"]), str(u)) for u in line["units"]]
    return out


def segment_responses(
    config: LakeConfig, source: str, season: int, raw_file: str, urls: Iterable[str]
) -> dict[str, list[Response]]:
    """The responses of ``urls`` in one raw segment file, by url (a refreshed segment can hold several).

    Only the row groups that hold one of the urls are read, and only their matching rows are kept, so memory
    follows one row group, not the whole segment.
    """
    path = config.raw_root / source / f"season={season}" / raw_file
    wanted = pa.array(sorted(set(urls)), pa.string())
    parquet = pq.ParquetFile(path)
    out: dict[str, list[Response]] = {}
    for group in range(parquet.num_row_groups):
        names = parquet.read_row_group(group, columns=["url"]).column("url")
        if not pc.any(pc.is_in(names, value_set=wanted)).as_py():
            continue
        table = parquet.read_row_group(
            group, columns=["url", "fetched_at", "status", "etag", "body"]
        )
        table = table.filter(pc.is_in(table.column("url"), value_set=wanted))
        for row in table.to_pylist():
            out.setdefault(str(row["url"]), []).append(
                Response(
                    url=str(row["url"]),
                    body=bytes(row["body"]),
                    fetched_at=str(row["fetched_at"]),
                    status=int(row["status"]),
                    etag=str(row["etag"] or ""),
                )
            )
    return out


def lineage_hashes(config: LakeConfig, spec: DatasetSpec, season: int | None) -> frozenset[str]:
    """The sha256 of every raw answer the processed rows of one season say they were made from."""
    folder = config.processed_dir(spec.source, spec.name, season)
    if not folder.is_dir():
        return frozenset()
    found: set[str] = set()
    for path in sorted(folder.glob("*.parquet")):
        if path.name.startswith("_") or LINEAGE_COLUMN not in pq.read_schema(path).names:
            continue
        column = pq.read_table(path, columns=[LINEAGE_COLUMN]).column(LINEAGE_COLUMN)
        found.update(str(v) for v in pc.unique(column).to_pylist() if v is not None)
    return frozenset(found)


__all__ = [
    "SegmentUnit",
    "lineage_hashes",
    "records_table",
    "scalar_text",
    "segment_responses",
    "segment_units",
]
