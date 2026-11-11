"""Convert the old per-dataset raw files of one source and season into raw segments (ADR 95).

Today one HTTP answer that feeds several datasets is saved once per dataset (a live feed four times, a
box score six times). A raw segment (``raw/<source>/season=Y/seg-NNNN.parquet``) holds one row per distinct URL
and body, with ``legacy_path`` naming every old file the row replaces. Nothing is lost: when a URL was
fetched on different days and the bytes differ, both bodies are kept (design 5b).

The steps of a real run, per season:

1. read every old file with its manifest entry and check the sha256 of the original bytes; one that does not
   match (or has no URL) is reported in ``skipped`` and the season writes and removes nothing;
2. write the distinct bodies not yet in a segment as raw segment files (bounded size, ``segment_bytes`` each);
3. read every new file back (each row's body hashes to its sha256, and every old file's URL and bytes are
   present); a failure deletes the new files and keeps everything;
4. append one commit line per new segment (the moment it counts);
5. only with ``remove_old``: delete the old files and mark their manifest entries ``stored: segment``.

A dry run reads manifests only. A rerun writes nothing that is already in a segment. One writer per source and
season (the host lock of ``core/hostlock.py``).
"""

import logging
import zlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.config import LakeConfig
from baseballpy.core.hostlock import release_named
from baseballpy.core.responselog import (
    RAW_SCHEMA,
    RawSegmentSink,
    ResponseLog,
    _segment_name,
    append_commit_line,
    file_sha256,
)
from baseballpy.core.segments import claim_season
from baseballpy.core.stores import RawStore, schema_fingerprint

logger = logging.getLogger(__name__)

#: uncompressed body bytes per raw segment file written by the converter (bounds memory)
SEGMENT_BYTES = 256 * 1024 * 1024


@dataclass
class SegmentConvertReport:
    """What one conversion run saw and did."""

    files: int = 0
    urls: int = 0
    copies: int = 0
    distinct_bodies: int = 0
    differing_urls: int = 0
    bytes_before: int = 0
    segments: list[str] = field(default_factory=list)
    removed: int = 0
    skipped: dict[str, str] = field(default_factory=dict)
    verified: bool = False


@dataclass(frozen=True)
class _OldFile:
    dataset: str
    name: str
    entry: dict[str, Any]

    @property
    def label(self) -> str:
        return f"{self.dataset}/{self.name}"

    @property
    def pair(self) -> tuple[str, str]:
        return str(self.entry["source_ref"]), str(self.entry["sha256"])


def _old_files(
    config: LakeConfig, source: str, season: int
) -> tuple[list[_OldFile], dict[str, str]]:
    """The old raw files of a season that a manifest records, and why some cannot be converted."""
    root = config.raw_root / source
    found: list[_OldFile] = []
    skipped: dict[str, str] = {}
    if not root.is_dir():
        return found, skipped
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")):
        if not (folder / f"season={season}").is_dir():
            continue
        manifest = config.dataset_manifest(source, folder.name, "raw", season)
        for name, entry in sorted(manifest.chunks().items()):
            if entry.get("stored") == "segment":
                continue  # already converted and removed
            if entry.get("status") != "COMPLETED" or not entry.get("sha256"):
                continue  # a commit marker or a failed fetch: not a file
            old = _OldFile(folder.name, name, entry)
            if not entry.get("source_ref"):
                skipped[old.label] = "no url (source_ref) in the manifest entry"
            else:
                found.append(old)
    return found, skipped


def _held_pairs(season_dir: Path) -> set[tuple[str, str]]:
    """The (url, sha256) pairs the raw segments of the season already hold."""
    held: set[tuple[str, str]] = set()
    for path in sorted(season_dir.glob("seg-*.parquet")):
        table = pq.read_table(path, columns=["url", "sha256"])
        held.update(zip(table["url"].to_pylist(), table["sha256"].to_pylist(), strict=True))
    return held


def _read_back_failures(
    season_dir: Path, expected: set[tuple[str, str]], files: list[str]
) -> list[str]:
    """Why the segment files cannot stand in for the old files (empty when they can)."""
    import hashlib

    failures: list[str] = []
    present: set[tuple[str, str]] = set()
    for name in files:
        path = season_dir / name
        try:
            table = pq.read_table(path)
        except (OSError, pa.ArrowInvalid) as exc:
            failures.append(f"{name}: unreadable ({exc})")
            continue
        for index, row in enumerate(table.to_pylist()):
            if hashlib.sha256(row["body"]).hexdigest() != row["sha256"]:
                failures.append(f"{name} row {index}: body does not match its sha256")
            present.add((row["url"], row["sha256"]))
    missing = expected - present
    if missing:
        failures.append(f"{len(missing)} old file body(ies) are not in the segments")
    return failures


def _table_of(rows: list[dict[str, Any]]) -> pa.Table:
    return pa.Table.from_pylist(rows, schema=RAW_SCHEMA)


def convert_raw_to_segments(
    config: LakeConfig,
    source: str,
    season: int,
    *,
    dry_run: bool = True,
    remove_old: bool = False,
    segment_bytes: int = SEGMENT_BYTES,
) -> SegmentConvertReport:
    """Convert the old raw files of ``source`` and ``season`` to raw segments (see the module docstring)."""
    report = SegmentConvertReport()
    files, report.skipped = _old_files(config, source, season)
    groups: dict[tuple[str, str], list[_OldFile]] = defaultdict(list)
    for old in files:
        groups[old.pair].append(old)
    bodies_of_url: dict[str, set[str]] = defaultdict(set)
    for url, sha in groups:
        bodies_of_url[url].add(sha)
    report.files = len(files)
    report.urls = len(bodies_of_url)
    report.distinct_bodies = len(groups)
    report.copies = len(files) - len(groups)
    report.differing_urls = sum(1 for shas in bodies_of_url.values() if len(shas) > 1)
    report.bytes_before = sum(int(old.entry.get("bytes") or 0) for old in files)
    if dry_run:
        return report

    claim_season(config, source, season)
    lock = f"segments-{source}-{season}"
    try:
        return _convert(config, source, season, groups, files, report, remove_old, segment_bytes)
    finally:
        release_named(config.locks_root, lock)


def _convert(
    config: LakeConfig,
    source: str,
    season: int,
    groups: dict[tuple[str, str], list[_OldFile]],
    files: list[_OldFile],
    report: SegmentConvertReport,
    remove_old: bool,
    segment_bytes: int,
) -> SegmentConvertReport:
    raw = RawStore(config)
    # step 1: every sha256 against the manifest, before anything is written
    for old in files:
        try:
            body = raw.get(source, old.dataset, old.name, season)
        except FileNotFoundError:
            report.skipped[old.label] = "the file is missing"
            continue
        except (OSError, EOFError, zlib.error) as exc:  # a torn or damaged gzip file
            report.skipped[old.label] = f"unreadable, so its sha256 cannot be checked ({exc})"
            continue
        import hashlib

        if hashlib.sha256(body).hexdigest() != old.entry["sha256"]:
            report.skipped[old.label] = "sha256 differs from the manifest"
    if report.skipped:
        return report

    log = ResponseLog(config, source, season)
    season_dir = log.season_dir
    held = _held_pairs(season_dir) if season_dir.is_dir() else set()
    todo = sorted(pair for pair in groups if pair not in held)

    # step 2: write the new bodies as bounded segment files (not yet committed)
    written: list[tuple[str, dict[str, Any]]] = []
    number = log.next_segment()
    batch: list[dict[str, Any]] = []
    size = 0

    def flush() -> None:
        nonlocal number, batch, size
        if not batch:
            return
        name = _segment_name(number)
        table = _table_of(batch)
        RawSegmentSink().write(table, str(season_dir / name))
        info = {
            "sha256": file_sha256(season_dir / name),
            "rows": table.num_rows,
        }
        written.append((name, {"units": sorted({row["url"] for row in batch}), "info": info}))
        number += 1
        batch, size = [], 0

    for pair in todo:
        sources_of_pair = groups[pair]
        first = sources_of_pair[0]
        body = raw.get(source, first.dataset, first.name, season)
        newest = max(sources_of_pair, key=lambda o: str(o.entry.get("fetched_at") or ""))
        batch.append(
            {
                "url": pair[0],
                "fetched_at": str(newest.entry.get("fetched_at") or ""),
                "status": 200,
                "etag": str(newest.entry.get("etag") or ""),
                "sha256": pair[1],
                "body": body,
                "legacy_path": ",".join(sorted(old.label for old in sources_of_pair)),
            }
        )
        size += len(body)
        if size >= segment_bytes:
            flush()
    flush()

    # step 3: read everything back before anything counts
    all_files = (
        sorted(p.name for p in season_dir.glob("seg-*.parquet")) if season_dir.is_dir() else []
    )
    failures = _read_back_failures(season_dir, set(groups), all_files)
    if failures:
        for name, _ in written:
            (season_dir / name).unlink(missing_ok=True)
        for failure in failures[:5]:
            logger.warning("raw conversion of %s %s rolled back: %s", source, season, failure)
        return report

    # step 4: the commit lines
    for name, data in written:
        append_commit_line(
            log.commit_path,
            {
                "segment": int(name.removeprefix("seg-").removesuffix(".parquet")),
                "units": data["units"],
                "raw": name,
                "files": {name: data["info"]},
                "schema_sha256": {"raw": schema_fingerprint(RAW_SCHEMA)},
                "committed_at": datetime.now(UTC).isoformat(),
                "legacy": True,
            },
        )
        report.segments.append(name)
    report.verified = True

    # step 5: the old files go, and their entries say where the bytes are now
    if remove_old:
        for old in files:
            path = raw.stored_path(source, old.dataset, old.name, season)
            if path is not None:
                path.unlink()
            entry = {k: v for k, v in old.entry.items() if k != "sha256"}
            entry.update({"stored": "segment", "segment_sha256": old.entry["sha256"]})
            config.dataset_manifest(source, old.dataset, "raw", season).put_entry(old.name, entry)
            report.removed += 1
    return report


__all__ = ["SEGMENT_BYTES", "SegmentConvertReport", "convert_raw_to_segments"]
