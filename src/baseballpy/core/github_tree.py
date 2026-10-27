"""Discover the files of a GitHub-hosted source from its git tree (cached under ``cache/http``)."""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from baseballpy.core.atomic import atomic_write
from baseballpy.core.config import LakeConfig
from baseballpy.core.http import HttpClient, get_http_client
from baseballpy.core.sources_lock import API_HOST, SourceRef, github_headers

logger = logging.getLogger(__name__)

#: Floating refs (branches) are re-listed after this many seconds; pinned SHAs never expire.
TREE_TTL_SECONDS = 86400


@dataclass(frozen=True)
class TreeEntry:
    """One blob of the repository tree."""

    path: str
    size: int
    sha: str


class TreeTruncatedError(RuntimeError):
    """GitHub truncated the recursive tree listing (too many entries)."""


def _cache_path(config: LakeConfig, ref: SourceRef) -> Path:
    safe = ref.repo.replace("/", "__")
    return config.http_cache_root / "github-tree" / f"{safe}@{ref.ref}.json"


def _read_cache(path: Path, ref: SourceRef, now: float) -> list[TreeEntry] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not ref.pinned and now - float(payload.get("fetched_at", 0)) > TREE_TTL_SECONDS:
        return None
    return [TreeEntry(e["path"], int(e["size"]), e["sha"]) for e in payload.get("entries", [])]


def fetch_tree(
    ref: SourceRef,
    config: LakeConfig | None = None,
    http: HttpClient | None = None,
    *,
    refresh: bool = False,
) -> list[TreeEntry]:
    """Every blob in ``ref``'s tree (``GET /git/trees/<ref>?recursive=1`` through the HttpClient).

    The listing is cached in ``cache/http/github-tree`` (safe to delete): forever for a pinned
    commit SHA, 24 hours for a branch. ``GITHUB_TOKEN`` is used when set.
    """
    cfg = config or LakeConfig()
    cache = _cache_path(cfg, ref)
    now = time.time()
    if not refresh and (cached := _read_cache(cache, ref, now)) is not None:
        return cached
    client = http or get_http_client()
    result = client.get_sync(
        f"{API_HOST}/repos/{ref.repo}/git/trees/{ref.ref}?recursive=1", headers=github_headers()
    )
    payload = result.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("tree"), list):
        raise ValueError(f"unexpected git tree response for {ref.repo}@{ref.ref}")
    if payload.get("truncated"):
        raise TreeTruncatedError(f"git tree for {ref.repo}@{ref.ref} is truncated")
    entries = [
        TreeEntry(str(node["path"]), int(node.get("size", 0)), str(node.get("sha", "")))
        for node in payload["tree"]
        if node.get("type") == "blob"
    ]
    body = json.dumps(
        {
            "fetched_at": now,
            "repo": ref.repo,
            "ref": ref.ref,
            "entries": [{"path": e.path, "size": e.size, "sha": e.sha} for e in entries],
        }
    )
    with atomic_write(cache, mode="w") as part:
        part.write_text(body, encoding="utf-8")
    return entries
