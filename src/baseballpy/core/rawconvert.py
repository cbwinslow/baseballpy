"""Convert existing raw text files to gzip (the form new downloads already use).

Every file is checked against the sha256 in its manifest, written compressed, read back and
checked again, and only then does the manifest say ``stored: gzip`` and the original go.
Run it when no ingest is running.
"""

import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from baseballpy.core.atomic import atomic_write
from baseballpy.core.config import LakeConfig
from baseballpy.core.rawfiles import (
    GZIP,
    GZIP_SUFFIX,
    gzip_bytes,
    is_compressible,
    is_packed,
    logical_sha256,
)

logger = logging.getLogger(__name__)

WORKERS = 16


@dataclass
class ConvertReport:
    """Totals of one conversion run."""

    files: int = 0
    bytes_before: int = 0
    bytes_after: int = 0
    skipped: list[str] = field(default_factory=list)


def _convert_directory(manifest_path: Path, *, dry_run: bool, config: LakeConfig) -> ConvertReport:
    report = ConvertReport()
    manifest = config.manifest_for_path(manifest_path)
    folder = manifest_path.parent
    updates: dict[str, dict[str, Any]] = {}
    originals: list[Path] = []
    for name, entry in sorted(manifest.chunks().items()):
        if (
            entry.get("status") != "COMPLETED"
            or "sha256" not in entry
            or is_packed(entry)
            or not is_compressible(name)
        ):
            continue
        plain = folder / name
        if not plain.exists():
            continue
        size = plain.stat().st_size
        if dry_run:
            report.files += 1
            report.bytes_before += size
            continue
        data = plain.read_bytes()
        if logical_sha256(plain, name) != entry["sha256"]:
            report.skipped.append(f"{plain}: sha256 differs from the manifest, left as it is")
            continue
        packed = plain.with_name(plain.name + GZIP_SUFFIX)
        blob = gzip_bytes(data)
        with atomic_write(packed) as part:
            part.write_bytes(blob)
        if logical_sha256(packed, name) != entry["sha256"]:
            packed.unlink(missing_ok=True)
            report.skipped.append(f"{plain}: compressed copy did not read back equal")
            continue
        updates[name] = {**entry, "stored": GZIP, "stored_bytes": len(blob)}
        originals.append(plain)
        report.files += 1
        report.bytes_before += size
        report.bytes_after += len(blob)
    if updates:
        manifest.put_entries(updates)  # one save: the manifest now points at the compressed files
        for plain in originals:
            plain.unlink()
    return report


def compress_raw(
    config: LakeConfig | None = None,
    *,
    sources: Iterable[str] | None = None,
    dry_run: bool = False,
    workers: int = WORKERS,
) -> ConvertReport:
    """Compress raw text files of ``sources`` (default: the configured ``raw_compress_sources``)."""
    cfg = config or LakeConfig()
    wanted = set(sources) if sources else set(cfg.raw_compress_sources)
    raw_root = cfg.raw_root
    manifests: list[Path] = []
    if raw_root.exists():
        for source_dir in sorted(p for p in raw_root.iterdir() if p.is_dir() and p.name in wanted):
            manifests.extend(sorted(source_dir.rglob("_manifest.json")))
    total = ConvertReport()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(
            lambda path: _convert_directory(path, dry_run=dry_run, config=cfg), manifests
        ):
            total.files += part.files
            total.bytes_before += part.bytes_before
            total.bytes_after += part.bytes_after
            total.skipped += part.skipped
    return total


__all__ = ["ConvertReport", "compress_raw"]
