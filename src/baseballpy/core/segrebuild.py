"""Rebuild a season's processed segment files from its raw segments (tasks 6.1 and 6.2 of response-log-segments).

The raw answers are already stored (by the converter or by an ingest); this module reads them again, with no
request, keeps the newest body of each URL (design 5b rule 3: every dataset cut from one URL agrees), groups the
answers by unit with the source's resolver, normalizes each unit with the current parsing function and writes the
processed files with :meth:`SegmentWriter.refresh`. The same path applies a schema change (ADR 87): run it with
``force=True`` and every segment is rebuilt.

The old part files of the season are moved to ``_legacy/`` (beside their dataset folder's files, under an
underscore name every reader skips) before any segment file appears, so a reader never sees both; a failure
puts them back. They are deleted only by :func:`remove_legacy`, after the row counts matched.
"""

from collections.abc import Collection, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow.parquet as pq

from baseballpy.core.config import LakeConfig
from baseballpy.core.responselog import Response, ResponseLog
from baseballpy.core.segments import ROW_GROUP_UNITS, Normalize, SegmentWriter, claim_season
from baseballpy.core.units import UnitResolver

LEGACY_DIRNAME = "_legacy"


@dataclass
class RebuildReport:
    """What one rebuild did (or, for a dry run, would do)."""

    segments: list[int] = field(default_factory=list)
    units: int = 0
    new_rows: dict[str, int] = field(default_factory=dict)
    old_rows: dict[str, int] = field(default_factory=dict)
    moved: int = 0
    restored: bool = False

    @property
    def matches(self) -> bool:
        """Whether every dataset that had old part files has the same number of rows now."""
        return all(self.new_rows.get(dataset) == rows for dataset, rows in self.old_rows.items())


def _season_folders(config: LakeConfig, source: str, season: int | None) -> list[Path]:
    base = config.processed_root / source
    if not base.is_dir():
        return []
    folders = [d if season is None else d / f"season={season}" for d in sorted(base.iterdir())]
    return [folder for folder in folders if folder.is_dir()]


def _old_files(folder: Path) -> list[Path]:
    """The files of the old layout: every Parquet file that is not a segment (``seg-*``)."""
    return sorted(p for p in folder.glob("*.parquet") if not p.name.startswith("seg-"))


def _newest_by_url(table: "object") -> list[Response]:
    """One response per URL: the newest ``fetched_at`` (the later row wins a tie)."""
    best: dict[str, Response] = {}
    for row in table.to_pylist():  # type: ignore[attr-defined]
        response = Response(
            url=row["url"],
            body=bytes(row["body"]),
            fetched_at=row["fetched_at"],
            status=int(row["status"]),
            etag=row["etag"] or "",
        )
        held = best.get(response.url)
        if held is None or response.fetched_at >= held.fetched_at:
            best[response.url] = response
    return list(best.values())


def _targets(log: ResponseLog, force: bool) -> dict[int, dict[str, object]]:
    """The committed segments to rebuild: every one with ``force``, else those without processed files."""
    out: dict[int, dict[str, object]] = {}
    for segment, line in sorted(log.latest_lines().items()):
        datasets = line.get("datasets") or {}
        if force or not any(info.get("file") for info in datasets.values()):
            out[segment] = line
    return out


def _units_of(
    log: ResponseLog, line: Mapping[str, object], unit_of: UnitResolver
) -> Mapping[str, Sequence[Response]]:
    table = pq.read_table(log.season_dir / str(line["raw"]))
    units: dict[str, list[Response]] = {}
    for response in _newest_by_url(table):
        units.setdefault(unit_of(response.url), []).append(response)
    if set(units) != set(line["units"]):  # type: ignore[call-overload]
        raise ValueError(
            f"segment {line['segment']}: the raw rows make units {sorted(units)[:3]}... but the commit line "
            f"names {sorted(line['units'])[:3]}...: the resolver is not the one the segment was written with"  # type: ignore[call-overload]
        )
    return units


def _old_row_counts(old_files: Mapping[Path, list[Path]], season: int | None) -> dict[str, int]:
    """Rows per dataset of the old part files: the visible ones and those already hidden in ``_legacy/``."""
    counts: dict[str, int] = {}
    for folder, files in old_files.items():
        dataset = folder.parent.name if season is not None else folder.name
        held = [*files, *sorted((folder / LEGACY_DIRNAME).glob("*.parquet"))]
        if held:
            counts[dataset] = sum(pq.ParquetFile(f).metadata.num_rows for f in held)
    return counts


def _committed_rows(log: ResponseLog) -> dict[str, int]:
    """Rows per dataset that the commit lines of every segment of the season name."""
    counts: dict[str, int] = {}
    for line in log.latest_lines().values():
        for dataset, info in (line.get("datasets") or {}).items():
            counts[dataset] = counts.get(dataset, 0) + int(info.get("rows") or 0)
    return counts


def rebuild_season(
    config: LakeConfig,
    source: str,
    season: int | None,
    normalize: Normalize,
    unit_of: UnitResolver,
    *,
    apply: bool = False,
    force: bool = False,
    row_group_units: int = ROW_GROUP_UNITS,
    datasets: Collection[str] | None = None,
) -> RebuildReport:
    """Rebuild the processed files of ``source`` and ``season`` from raw; a dry run only counts.

    ``datasets`` names the datasets the normalizer writes: only their old files are counted and hidden (a
    dataset the segments do not write keeps its files). ``None`` means every dataset of the source.
    """
    report = RebuildReport()
    claim_season(config, source, season)
    log = ResponseLog(config, source, season)
    targets = _targets(log, force)
    old_files: dict[Path, list[Path]] = {}
    for folder in _season_folders(config, source, season):
        name = folder.parent.name if season is not None else folder.name
        if datasets is None or name in datasets:
            old_files[folder] = _old_files(folder)
    report.old_rows = _old_row_counts(old_files, season)
    report.new_rows = _committed_rows(log)
    if not targets:
        return report
    if not apply:
        report.segments = list(targets)
        report.units = sum(len(line["units"]) for line in targets.values())  # type: ignore[arg-type, misc]
        return report
    moved: list[tuple[Path, Path]] = []
    try:
        for folder, files in old_files.items():
            for path in files:
                target = folder / LEGACY_DIRNAME / path.name
                target.parent.mkdir(exist_ok=True)
                path.replace(target)
                moved.append((path, target))
        report.moved = len(moved)
        writer = SegmentWriter(config, source, season, normalize, row_group_units=row_group_units)
        for segment, line in targets.items():
            units = _units_of(writer.log, line, unit_of)
            writer.refresh(segment, units)
            report.segments.append(segment)
            report.units += len(units)
        report.new_rows = _committed_rows(writer.log)
    except BaseException:
        if not report.segments:  # nothing was committed: put the old files back where readers look
            for original, hidden in reversed(moved):
                with suppress(OSError):
                    hidden.replace(original)
            report.restored = True
        # after progress the old files stay hidden (putting them back beside committed segments would
        # double count) and a rerun resumes with the segments that still have no processed files
        raise
    return report


def remove_legacy(
    config: LakeConfig, source: str, season: int | None, report: RebuildReport
) -> int:
    """Delete the hidden old files of a season, but only when the rebuild matched the old row counts.

    Returns the number of files removed; a mismatch raises and removes nothing.
    """
    if not report.matches or not report.new_rows:
        raise ValueError(
            f"the rebuilt row counts {report.new_rows} do not match the old files {report.old_rows}"
        )
    removed = 0
    for folder in _season_folders(config, source, season):
        legacy = folder / LEGACY_DIRNAME
        if legacy.is_dir():
            for path in legacy.glob("*.parquet"):
                path.unlink()
                removed += 1
            with suppress(OSError):
                legacy.rmdir()
    return removed


__all__ = ["LEGACY_DIRNAME", "RebuildReport", "rebuild_season", "remove_legacy"]
