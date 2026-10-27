"""Extractor for the sharded Chadwick Bureau Register from GitHub with commit SHA revalidation."""

import asyncio
import concurrent.futures
import logging
from pathlib import Path

import httpx

from baseballpy.core.atomic import ManifestTracker, atomic_write
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import CacheConfig, RateLimitConfig
from baseballpy.core.http import HttpClient, HttpStatusError, get_http_client

logger = logging.getLogger(__name__)

CHADWICK_DATA_BASE_URL = "https://raw.githubusercontent.com/chadwickbureau/register/master/data"
CHADWICK_COMMITS_API = (
    "https://api.github.com/repos/chadwickbureau/register/commits?path=data&page=1&per_page=1"
)
HEX_SHARDS = [f"people-{c}.csv" for c in "0123456789abcdef"]
AUXILIARY_FILES = ("names.csv", "links.csv")
SHA_CHUNK = "commit_sha"


class ChadwickExtractor:
    """Extracts all 16 sharded Chadwick Bureau Register files with SHA revalidation."""

    def __init__(
        self,
        cache_config: CacheConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        http: HttpClient | None = None,
    ) -> None:
        self.cache_config = cache_config or CacheConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.http = http or (
            HttpClient(self.rate_limit_config) if rate_limit_config else get_http_client()
        )
        self.manifest = ManifestTracker(self.cache_config.chadwick_dir / "manifest.json")

    @property
    def shards_dir(self) -> Path:
        """Directory holding the individual hex shard CSV files."""
        path = self.cache_config.chadwick_dir / "shards"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def names_file(self) -> Path:
        """Path for cached names.csv (nicknames and aliases)."""
        return self.cache_config.chadwick_dir / "names.csv"

    @property
    def links_file(self) -> Path:
        """Path for cached links.csv (external player links)."""
        return self.cache_config.chadwick_dir / "links.csv"

    def get_latest_commit_sha(self) -> str | None:
        """Query the GitHub API for the latest commit SHA of the data directory.

        Failures are logged (never silently ignored) and reported as ``None`` so callers can
        decide how to degrade.
        """
        try:
            result = self.http.get_sync(
                CHADWICK_COMMITS_API, headers={"Accept": "application/vnd.github+json"}
            )
            commits = result.json()
        except (HttpStatusError, httpx.TransportError, ValueError) as exc:
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
        if not self.names_file.exists():
            return False
        return all((self.shards_dir / shard).exists() for shard in HEX_SHARDS)

    def is_cache_current(self, refresh: bool) -> bool:
        """Apply the freshness policy; after the TTL, revalidate against the upstream SHA."""
        if refresh or not self.are_shards_cached():
            return False
        entry = self.manifest.get_chunk(SHA_CHUNK)
        if entry is None or entry.get("status") != "COMPLETED":
            return False
        if self.cache_config.is_fresh(entry, "chadwick"):
            return True
        latest = self.get_latest_commit_sha()
        if latest is None:
            logger.warning("serving possibly stale Chadwick register (SHA check failed)")
            return True
        if latest == entry.get("sha"):
            self.manifest.set_completed(
                SHA_CHUNK,
                records_count=int(entry.get("records_count", 0)),
                metadata={"sha": latest},
            )
            return True
        logger.info("Chadwick register changed upstream (%s); re-downloading", latest)
        return False

    def _download(self, filename: str, target: Path, required: bool) -> bytes | None:
        result = self.http.get_sync(
            f"{CHADWICK_DATA_BASE_URL}/{filename}", allow=(200,) if required else (200, 404)
        )
        if result.status == 404:
            return None
        with atomic_write(target) as part_path:
            part_path.write_bytes(result.content)
        return result.content

    def extract(self, refresh: bool = False) -> dict[str, bytes]:
        """Download all 16 hex shards and auxiliary files, or load from a current cache.

        A missing shard is a hard error: a partial register would silently lose players.
        """
        with default_audit_logger.track(
            operation="chadwick_extract_shards",
            source="chadwick",
            endpoint=CHADWICK_DATA_BASE_URL,
            destination=str(self.shards_dir),
        ) as tracker:
            if self.is_cache_current(refresh):
                tracker.set_cache_hit(True)
                return self._read_cached_files()

            latest_sha = self.get_latest_commit_sha()
            jobs: list[tuple[str, Path, bool]] = [
                (shard, self.shards_dir / shard, True) for shard in HEX_SHARDS
            ]
            jobs.append(("names.csv", self.names_file, False))
            jobs.append(("links.csv", self.links_file, False))

            results: dict[str, bytes] = {}
            workers = max(1, self.rate_limit_config.max_concurrency)
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    name: pool.submit(self._download, name, target, required)
                    for name, target, required in jobs
                }
                for name, future in futures.items():
                    content = future.result()
                    if content is not None:
                        results[name] = content

            self.manifest.set_completed(
                SHA_CHUNK,
                records_count=len(results),
                metadata={"sha": latest_sha or ""},
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
        for name, path in (("names.csv", self.names_file), ("links.csv", self.links_file)):
            if path.exists():
                files[name] = path.read_bytes()
        return files
