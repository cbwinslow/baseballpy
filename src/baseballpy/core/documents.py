"""Keep a provider's documentation files (README, licence, data dictionary) next to its data.

Every source hosted in git offers files that are not data but explain it and say how it may be used.
They are kept in ``raw/<source>/<dataset>/`` with their sha256 and git fingerprint, found by matching
the git tree listing against patterns (so a yearly renamed ``readme2025.txt`` is still found). A
failed download is logged and never blocks the data.
"""

import logging
from collections.abc import Mapping, Sequence
from fnmatch import fnmatchcase
from pathlib import PurePosixPath

from baseballpy.core.config import LakeConfig
from baseballpy.core.github_tree import TreeEntry, TreeTruncatedError, fetch_tree
from baseballpy.core.http import HttpClient, HttpStatusError, TransportError
from baseballpy.core.sources_lock import SourceRef
from baseballpy.core.stores import RawStore
from baseballpy.core.upstream import GIT_BLOB, Fingerprint, response_fingerprint

logger = logging.getLogger(__name__)


def tree_or_none(
    ref: SourceRef, config: LakeConfig, http: HttpClient, *, what: str
) -> list[TreeEntry] | None:
    """The git tree of ``ref``, or ``None`` after a logged warning when it cannot be listed."""
    try:
        return fetch_tree(ref, config, http)
    except (HttpStatusError, TransportError, ValueError, TreeTruncatedError) as exc:
        logger.warning("could not list %s from the git tree of %s: %s", what, ref.repo, exc)
        return None


def document_paths(entries: Sequence[TreeEntry], patterns: Sequence[str]) -> list[TreeEntry]:
    """The tree entries whose path matches one of the shell-style ``patterns`` (case sensitive)."""
    return [e for e in entries if any(fnmatchcase(e.path, p) for p in patterns)]


def keep_documents(
    *,
    raw: RawStore,
    http: HttpClient,
    ref: SourceRef,
    entries: Sequence[TreeEntry],
    source: str,
    dataset: str,
    patterns: Sequence[str],
    source_ref: str | None,
    only_missing: bool,
) -> list[str]:
    """Store the matching documentation files in ``raw/<source>/<dataset>/``; returns their names.

    With ``only_missing`` a file that is already there is left alone (a cached run downloads
    nothing). A download that fails is logged and skipped.
    """
    kept: list[str] = []
    for entry in document_paths(entries, patterns):
        name = PurePosixPath(entry.path).name
        if only_missing and raw.path_for(source, dataset, name).exists():
            continue
        try:
            result = http.get_sync(f"{ref.raw_base()}/{entry.path}")
        except (HttpStatusError, TransportError) as exc:
            logger.warning("could not download %s document %s: %s", source, entry.path, exc)
            continue
        raw.put(
            source,
            dataset,
            name,
            result.content,
            source_ref=source_ref,
            etag=result.etag or "",
            upstream=Fingerprint(GIT_BLOB, entry.sha, origin=f"{ref.repo}:{entry.path}"),
        )
        kept.append(name)
    return kept


def keep_pages(
    *,
    raw: RawStore,
    http: HttpClient,
    source: str,
    dataset: str,
    pages: Mapping[str, str],
    source_ref: str | None,
    only_missing: bool,
) -> list[str]:
    """Store documentation pages of a source that is not hosted in git (``{file name: url}``).

    Each page is kept as served, with its sha256 and the ETag (or the content hash) as its upstream
    fingerprint. With ``only_missing`` a page already stored is left alone. A failed download is
    logged and skipped.
    """
    kept: list[str] = []
    for name, url in pages.items():
        if only_missing and raw.path_for(source, dataset, name).exists():
            continue
        try:
            result = http.get_sync(url)
        except (HttpStatusError, TransportError) as exc:
            logger.warning("could not download %s document %s: %s", source, url, exc)
            continue
        raw.put(
            source,
            dataset,
            name,
            result.content,
            source_ref=source_ref,
            etag=result.etag or "",
            upstream=response_fingerprint(result.content, result.etag, url),
        )
        kept.append(name)
    return kept


__all__ = ["document_paths", "keep_documents", "keep_pages", "tree_or_none"]
