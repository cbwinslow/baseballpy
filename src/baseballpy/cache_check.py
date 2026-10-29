"""Check the raw tier of the lake: are the files intact, and have their upstream versions changed?

Integrity compares every raw file with the sha256 its manifest recorded (offline). The optional
upstream check compares the git blob fingerprints stored at download time with the latest tree of
each repository (two GitHub requests per repository, the tree listing is cached by commit).
"""

import hashlib
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from baseballpy.core.atomic import ManifestTracker
from baseballpy.core.config import LakeConfig
from baseballpy.core.github_tree import TreeTruncatedError, fetch_tree
from baseballpy.core.http import HttpStatusError, TransportError
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def latest_blobs(config: LakeConfig) -> LatestBlobs:
    """A :data:`LatestBlobs` that asks GitHub for the latest commit and lists its tree."""

    def lookup(repo: str) -> Mapping[str, str]:
        sha = resolve_latest_sha(repo)
        entries = fetch_tree(SourceRef("check", repo, sha), config)
        return {e.path: e.sha for e in entries}

    return lookup


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
    for manifest_path in sorted(raw_root.rglob("manifest.json")):
        source, dataset, season = _location(raw_root, manifest_path.parent)
        if sources and source not in sources:
            continue
        for name, entry in sorted(ManifestTracker(manifest_path).chunks().items()):
            if entry.get("status") != "COMPLETED" or "sha256" not in entry:
                continue
            path = manifest_path.parent / name
            if not path.exists():
                integrity = MISSING
            else:
                integrity = OK if _sha256(path) == entry["sha256"] else CORRUPT
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
