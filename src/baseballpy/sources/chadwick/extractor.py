"""Extractor for the Chadwick Bureau Register: tree-driven discovery, pinned refs, SHA revalidation."""

import asyncio
import concurrent.futures
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from baseballpy.core.atomic import cleanup_stale_parts
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.github_tree import TreeTruncatedError, fetch_tree
from baseballpy.core.http import HttpClient, HttpStatusError, TransportError, get_http_client
from baseballpy.core.sources_lock import SourceRef, get_source_ref, github_headers
from baseballpy.core.stores import RawStore

logger = logging.getLogger(__name__)

#: Default (pinned) data URL; instances derive theirs from the lock / env override.
CHADWICK_DATA_BASE_URL = f"{get_source_ref('chadwick_register').raw_base()}/data"
CHADWICK_COMMITS_API = (
    "https://api.github.com/repos/chadwickbureau/register/commits?path=data&page=1&per_page=1"
)
HEX_SHARDS = [f"people-{c}.csv" for c in "0123456789abcdef"]
AUXILIARY_FILES = ("names.csv", "links.csv", "countries.csv")
SHA_CHUNK = "commit_sha"

#: file name (in ``data/``) -> dataset whose ``raw/chadwick/<dataset>/`` directory stores it
AUXILIARY_DATASETS = {
    "names.csv": "register_names",
    "links.csv": "register_links",
    "countries.csv": "register_countries",
}
#: Repository-root documents kept next to the shards in ``raw/chadwick/register/`` (they explain the
#: id systems and the key rules); they are fetched only when the git tree lists them.
DOCUMENT_FILES = ("README.md",)
_SHARD = re.compile(r"^people-[0-9a-f]\.csv$")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ChadwickExtractor:
    """Extracts the sharded Chadwick Register and its auxiliary files at a pinned commit."""

    def __init__(
        self,
        cache_config: LakeConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        http: HttpClient | None = None,
        ref: str | None = None,
    ) -> None:
        self.cache_config = cache_config or LakeConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.http = http or (
            HttpClient(self.rate_limit_config) if rate_limit_config else get_http_client()
        )
        locked = get_source_ref("chadwick_register", self.cache_config.home)
        self.source_ref = SourceRef(locked.key, locked.repo, ref) if ref else locked
        self.data_base_url = f"{self.source_ref.raw_base()}/data"
        self.manifest = self.cache_config.dataset_manifest("chadwick", "register", "raw")
        self.raw = RawStore(self.cache_config)
        # discard orphaned .part files from killed runs
        cleanup_stale_parts(self.cache_config.raw_root / "chadwick")

    @property
    def shards_dir(self) -> Path:
        """Directory holding the individual hex shard CSV files (``raw/chadwick/register``)."""
        return self.cache_config.raw_dir("chadwick", "register")

    @property
    def names_file(self) -> Path:
        """Path for cached names.csv (nicknames and aliases)."""
        return self.cache_config.raw_dir("chadwick", "register_names") / "names.csv"

    @property
    def links_file(self) -> Path:
        """Path for cached links.csv (external player identifiers)."""
        return self.cache_config.raw_dir("chadwick", "register_links") / "links.csv"

    @property
    def countries_file(self) -> Path:
        """Path for cached countries.csv (ISO/IOC/FIFA country codes)."""
        return self.cache_config.raw_dir("chadwick", "register_countries") / "countries.csv"

    def _raw_path(self, filename: str) -> Path:
        if _SHARD.match(filename):
            return self.shards_dir / filename
        dataset = AUXILIARY_DATASETS[filename]
        return self.cache_config.raw_dir("chadwick", dataset) / filename

    def discover_files(self, refresh: bool = False) -> list[str]:
        """File names under ``data/`` that belong to the register, discovered from the git tree.

        A tree that lacks any of the 16 hex shards is a hard error (a partial register would
        silently lose players). Files in ``data/`` that no dataset covers are reported as coverage
        gaps. If the tree itself cannot be fetched, the known file list is used with a warning.
        """
        try:
            entries = fetch_tree(self.source_ref, self.cache_config, self.http, refresh=refresh)
        except (HttpStatusError, TransportError, ValueError, TreeTruncatedError) as exc:
            logger.warning(
                "could not discover Chadwick files from the git tree (%s); using the known list",
                exc,
            )
            return [*HEX_SHARDS, *AUXILIARY_FILES]
        names = sorted(
            e.path.removeprefix("data/")
            for e in entries
            if e.path.startswith("data/") and e.path.count("/") == 1
        )
        shards = [n for n in names if _SHARD.match(n)]
        missing = sorted(set(HEX_SHARDS) - set(shards))
        if missing:
            raise RuntimeError(f"Chadwick tree is missing register shard(s) {missing}")
        aux = [n for n in names if n in AUXILIARY_DATASETS]
        uncovered = [n for n in names if n not in shards and n not in aux and n.endswith(".csv")]
        if uncovered:
            logger.warning("Chadwick tree has data file(s) no dataset covers yet: %s", uncovered)
        return [*shards, *aux]

    def _fetch_documents(self, source_ref: str, *, only_missing: bool) -> None:
        """Keep the upstream documents the git tree lists (see ``DOCUMENT_FILES``).

        A failed download is logged and does not block the register: the data files are what the
        datasets are built from.
        """
        try:
            entries = fetch_tree(self.source_ref, self.cache_config, self.http)
        except (HttpStatusError, TransportError, ValueError, TreeTruncatedError) as exc:
            logger.warning("could not list Chadwick documents from the git tree: %s", exc)
            return
        listed = {e.path for e in entries}
        for name in DOCUMENT_FILES:
            if name not in listed or (only_missing and (self.shards_dir / name).exists()):
                continue
            try:
                result = self.http.get_sync(f"{self.source_ref.raw_base()}/{name}")
            except (HttpStatusError, TransportError) as exc:
                logger.warning("could not download Chadwick document %s: %s", name, exc)
                continue
            self.raw.put(
                "chadwick",
                "register",
                name,
                result.content,
                source_ref=source_ref or None,
                etag=result.etag or "",
            )

    def get_latest_commit_sha(self) -> str | None:
        """Query the GitHub API (authenticated when ``GITHUB_TOKEN`` is set) for the latest SHA.

        Failures are logged (never silently ignored) and reported as ``None`` so callers can
        decide how to degrade.
        """
        try:
            result = self.http.get_sync(CHADWICK_COMMITS_API, headers=github_headers())
            commits = result.json()
        except (HttpStatusError, TransportError, ValueError) as exc:
            logger.warning("could not determine latest Chadwick register commit: %s", exc)
            return None
        if isinstance(commits, list) and commits and isinstance(commits[0], dict):
            sha = commits[0].get("sha")
            if isinstance(sha, str):
                return sha
        logger.warning("unexpected GitHub commits response while checking Chadwick register")
        return None

    def are_shards_cached(self) -> bool:
        """Verify all 16 hex shards exist on disk."""
        return all((self.shards_dir / shard).exists() for shard in HEX_SHARDS)

    def _recorded_files_present(self, entry: dict[str, object]) -> bool:
        files = entry.get("files")
        names = [str(f) for f in files] if isinstance(files, list) else list(HEX_SHARDS)
        return all(self._raw_path(n).exists() for n in names)

    def is_cache_current(self, refresh: bool) -> bool:
        """Apply the freshness policy; after 24 h a floating ref is revalidated against upstream."""
        if refresh or not self.are_shards_cached():
            return False
        entry = self.manifest.get_chunk(SHA_CHUNK)
        if entry is None or entry.get("status") != "COMPLETED":
            return False
        if not self._recorded_files_present(entry):
            return False
        if self.source_ref.pinned:
            # reproducible mode: current iff fetched at exactly the locked commit
            return bool(entry.get("sha") == self.source_ref.ref)
        if self.cache_config.is_fresh(entry, "chadwick"):
            return True
        latest = self.get_latest_commit_sha()
        if latest is None:
            logger.warning("serving possibly stale Chadwick register (SHA check failed)")
            return True
        if latest == entry.get("sha"):
            self.manifest.put_entry(
                SHA_CHUNK, {**entry, "fetched_at": _now_iso(), "completed_at": _now_iso()}
            )
            return True
        logger.info("Chadwick register changed upstream (%s); re-downloading", latest)
        return False

    def _download(self, filename: str, source_ref: str) -> bytes:
        dataset = "register" if _SHARD.match(filename) else AUXILIARY_DATASETS[filename]
        result = self.http.get_sync(f"{self.data_base_url}/{filename}")
        self.raw.put(
            "chadwick",
            dataset,
            filename,
            result.content,
            source_ref=source_ref or None,
            etag=result.etag or "",
        )
        return result.content

    def extract(self, refresh: bool = False) -> dict[str, bytes]:
        """Download the 16 hex shards and auxiliary files, or load them from a current cache.

        A missing shard is a hard error: a partial register would silently lose players.
        """
        with default_audit_logger.track(
            operation="chadwick_extract_shards",
            source="chadwick",
            endpoint=self.data_base_url,
            destination=str(self.shards_dir),
        ) as tracker:
            if self.is_cache_current(refresh):
                tracker.set_cache_hit(True)
                self._fetch_documents(self.source_ref.ref, only_missing=True)
                return self._read_cached_files()

            files = self.discover_files(refresh=refresh)
            latest_sha = (
                self.source_ref.ref if self.source_ref.pinned else self.get_latest_commit_sha()
            )
            results: dict[str, bytes] = {}
            workers = max(1, self.rate_limit_config.max_concurrency)
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    name: pool.submit(self._download, name, latest_sha or "") for name in files
                }
                for name, future in futures.items():
                    results[name] = future.result()

            self._fetch_documents(latest_sha or "", only_missing=False)
            self.manifest.set_completed(
                SHA_CHUNK,
                records_count=len(results),
                metadata={"sha": latest_sha or "", "files": sorted(results)},
            )
            tracker.set_cache_hit(False)
            tracker.set_records(sum(len(b) for b in results.values()))
            return results

    async def extract_async(self, refresh: bool = False) -> dict[str, bytes]:
        """Asynchronously download shards (runs the shared, rate-limited sync path in a thread)."""
        return await asyncio.to_thread(self.extract, refresh)

    def _read_cached_files(self) -> dict[str, bytes]:
        """Load all shard and auxiliary bytes from cache."""
        files: dict[str, bytes] = {}
        for shard in HEX_SHARDS:
            path = self.shards_dir / shard
            if path.exists():
                files[shard] = path.read_bytes()
        for name in AUXILIARY_FILES:
            path = self._raw_path(name)
            if path.exists():
                files[name] = path.read_bytes()
        return files
