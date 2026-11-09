"""Check the raw tier of the lake: are the files intact, and have their upstream versions changed?

Integrity compares every raw file with the sha256 its manifest recorded (offline). The optional
upstream check compares the git blob fingerprints stored at download time with the latest tree of
each repository (two GitHub requests per repository, the tree listing is cached by commit).

Segments (ADR 95) are checked by :func:`check_segments`: every file a commit line names must be there
and match its recorded sha256, and every row of a raw segment must hold the bytes its own sha256 names.
"""

import hashlib
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq

from baseballpy.core.atomic import ManifestTracker
from baseballpy.core.config import LakeConfig
from baseballpy.core.github_tree import TreeTruncatedError, fetch_tree
from baseballpy.core.http import HttpStatusError, TransportError
from baseballpy.core.rawfiles import logical_sha256, stored_path
from baseballpy.core.responselog import COMMIT_NAME, file_sha256, read_commit_lines
from baseballpy.core.sources_lock import SourceRef, resolve_latest_sha
from baseballpy.core.upstream import GIT_BLOB, stored_fingerprint

logger = logging.getLogger(__name__)

# integrity verdicts
OK = "ok"
CORRUPT = "corrupt"
MISSING = "missing"
# upstream verdicts
NOT_CHECKED = "not_checked"
NO_FINGERPRINT = "no_fingerprint"
CURRENT = "current"
CHANGED = "changed"
REMOVED = "removed"
UNREACHABLE = "unreachable"

#: ``repo -> {path: blob sha}`` of upstream's latest commit
LatestBlobs = Callable[[str], Mapping[str, str]]


@dataclass(frozen=True)
class FileCheck:
    """The verdicts for one raw file."""

    source: str
    dataset: str
    season: int | None
    name: str
    integrity: str
    upstream: str


def latest_blobs(config: LakeConfig) -> LatestBlobs:
    """A :data:`LatestBlobs` that asks GitHub for the latest commit and lists its tree."""

    def lookup(repo: str) -> Mapping[str, str]:
        sha = resolve_latest_sha(repo)
        entries = fetch_tree(SourceRef("check", repo, sha), config)
        return {e.path: e.sha for e in entries}

    return lookup


def _raw_rows_ok(path: Path) -> bool:
    """True when every row of a raw segment holds the bytes its own sha256 names."""
    with pq.ParquetFile(path) as handle:
        for batch in handle.iter_batches(columns=["sha256", "body"], batch_size=64):
            for sha, body in zip(
                batch.column("sha256").to_pylist(), batch.column("body").to_pylist(), strict=True
            ):
                if hashlib.sha256(body).hexdigest() != sha:
                    return False
    return True


def _file_verdict(path: Path, expected_sha256: str, *, raw_rows: bool = False) -> str:
    if not path.is_file():
        return MISSING
    try:
        if file_sha256(path) != expected_sha256:
            return CORRUPT
        if raw_rows and not _raw_rows_ok(path):
            return CORRUPT
    except (OSError, ValueError, pq.lib.ArrowException):
        return CORRUPT  # unreadable counts as damaged
    return OK


def check_segments(config: LakeConfig, *, sources: Sequence[str] = ()) -> list[FileCheck]:
    """Verdicts for every file the newest commit line of each segment names.

    Raw segment: the file against the line's sha256 and every row's body against the row's sha256.
    Processed segment files: the file against the line's sha256. The upstream verdict is
    ``not_checked``: segments carry no git fingerprint.
    """
    results: list[FileCheck] = []
    raw_root = config.raw_root
    for commit_path in sorted(raw_root.rglob(COMMIT_NAME)):
        source, _, season = _location(raw_root, commit_path.parent)
        if sources and source not in sources:
            continue
        lines, _ = read_commit_lines(commit_path)
        for line in {int(x["segment"]): x for x in lines}.values():
            for name, info in sorted(line.get("files", {}).items()):
                verdict = _file_verdict(commit_path.parent / name, info["sha256"], raw_rows=True)
                results.append(
                    FileCheck(source, "(raw segments)", season, name, verdict, NOT_CHECKED)
                )
            for dataset, info in sorted(line.get("datasets", {}).items()):
                if not info.get("file"):
                    continue  # the segment has no rows for this dataset
                folder = config.processed_dir(source, dataset, season)
                verdict = _file_verdict(folder / info["file"], info["sha256"])
                results.append(
                    FileCheck(source, dataset, season, info["file"], verdict, NOT_CHECKED)
                )
    return results


def _location(raw_root: Path, directory: Path) -> tuple[str, str, int | None]:
    parts = directory.relative_to(raw_root).parts
    season = None
    if parts and parts[-1].startswith("season="):
        season = int(parts[-1].removeprefix("season="))
        parts = parts[:-1]
    source = parts[0] if parts else ""
    dataset = "/".join(parts[1:])
    return source, dataset, season


def check_raw(
    config: LakeConfig,
    *,
    sources: Sequence[str] = (),
    upstream: bool = False,
    latest: LatestBlobs | None = None,
) -> list[FileCheck]:
    """Verdicts for every raw file recorded in a manifest (files without a recorded sha256, such as
    commit markers, are not files and are skipped).

    With ``upstream=True`` the git blob fingerprints are compared with ``latest`` (default: GitHub).
    """
    lookup = latest or latest_blobs(config)
    trees: dict[str, Mapping[str, str] | None] = {}
    results: list[FileCheck] = []
    raw_root = config.raw_root
    for manifest_path in sorted(
        {*raw_root.rglob("_manifest.json"), *raw_root.rglob("manifest.json")}
    ):
        source, dataset, season = _location(raw_root, manifest_path.parent)
        if sources and source not in sources:
            continue
        for name, entry in sorted(ManifestTracker(manifest_path).chunks().items()):
            if entry.get("status") != "COMPLETED" or "sha256" not in entry:
                continue
            path = stored_path(manifest_path.parent, name)
            if path is None:
                integrity = MISSING
            else:
                integrity = OK if logical_sha256(path, name) == entry["sha256"] else CORRUPT
            results.append(
                FileCheck(
                    source,
                    dataset,
                    season,
                    name,
                    integrity,
                    _upstream_verdict(entry, upstream, lookup, trees),
                )
            )
    return results


def _upstream_verdict(
    entry: Mapping[str, object],
    upstream: bool,
    lookup: LatestBlobs,
    trees: dict[str, Mapping[str, str] | None],
) -> str:
    if not upstream:
        return NOT_CHECKED
    fingerprint = stored_fingerprint(entry)
    if fingerprint is None:
        return NO_FINGERPRINT
    if fingerprint.kind != GIT_BLOB or ":" not in fingerprint.origin:
        return NOT_CHECKED
    repo, path = fingerprint.origin.split(":", 1)
    if repo not in trees:
        try:
            trees[repo] = lookup(repo)
        except (HttpStatusError, TransportError, ValueError, TreeTruncatedError) as exc:
            logger.warning("could not list the latest tree of %s: %s", repo, exc)
            trees[repo] = None
    tree = trees[repo]
    if tree is None:
        return UNREACHABLE
    if path not in tree:
        return REMOVED
    return CURRENT if tree[path] == fingerprint.value else CHANGED


__all__ = [
    "CHANGED",
    "CORRUPT",
    "CURRENT",
    "MISSING",
    "NOT_CHECKED",
    "NO_FINGERPRINT",
    "OK",
    "REMOVED",
    "UNREACHABLE",
    "FileCheck",
    "LatestBlobs",
    "check_raw",
    "latest_blobs",
]
