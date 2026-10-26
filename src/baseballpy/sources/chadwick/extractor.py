"""Extractor for the sharded Chadwick Bureau Register from GitHub with commit SHA tracking."""

import asyncio
from pathlib import Path

import httpx

from baseballpy.core.atomic import ManifestTracker, atomic_write
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import CacheConfig, RateLimitConfig

CHADWICK_DATA_BASE_URL = "https://raw.githubusercontent.com/chadwickbureau/register/master/data"
CHADWICK_COMMITS_API = (
    "https://api.github.com/repos/chadwickbureau/register/commits?path=data&page=1&per_page=1"
)
HEX_SHARDS = [f"people-{c}.csv" for c in "0123456789abcdef"]


class ChadwickExtractor:
    """Extracts all 16 sharded Chadwick Bureau Register files with commit tracking and atomic gates."""

    def __init__(
        self,
        cache_config: CacheConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ) -> None:
        self.cache_config = cache_config or CacheConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
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

    def get_latest_commit_sha(self, client: httpx.Client | None = None) -> str | None:
        """Query GitHub API for latest commit SHA on data directory."""
        try:
            cli = client or httpx.Client(timeout=10.0)
            resp = cli.get(CHADWICK_COMMITS_API, headers={"User-Agent": "baseballpy"})
            if resp.status_code == 200:
                commits = resp.json()
                if commits and isinstance(commits, list) and "sha" in commits[0]:
                    sha = str(commits[0]["sha"])
                    return sha
        except Exception:
            return None
        return None

    def are_shards_cached(self) -> bool:
        """Verify all 16 hex shards exist on disk."""
        if not self.names_file.exists():
            return False
        return all((self.shards_dir / shard).exists() for shard in HEX_SHARDS)

    def extract(self, refresh: bool = False) -> dict[str, bytes]:
        """Download all 16 hex shards and auxiliary files, or load from cache."""
        with default_audit_logger.track(
            operation="chadwick_extract_shards",
            source="chadwick",
            endpoint=CHADWICK_DATA_BASE_URL,
            destination=str(self.shards_dir),
        ) as tracker:
            # Check if all files exist and are fresh
            latest_sha = None
            if not refresh and self.are_shards_cached():
                cached_sha = self.manifest.get_chunk("commit_sha")
                if cached_sha and cached_sha.get("sha"):
                    tracker.set_cache_hit(True)
                    return self._read_cached_files()

            # Network download
            with httpx.Client(timeout=self.rate_limit_config.timeout_seconds) as client:
                latest_sha = self.get_latest_commit_sha(client)

                results: dict[str, bytes] = {}
                for shard in HEX_SHARDS:
                    url = f"{CHADWICK_DATA_BASE_URL}/{shard}"
                    resp = client.get(url)
                    resp.raise_for_status()
                    content = resp.content
                    results[shard] = content

                    if self.cache_config.enabled:
                        shard_path = self.shards_dir / shard
                        with atomic_write(shard_path) as part_path:
                            part_path.write_bytes(content)

                # Download names.csv (nicknames & aliases)
                names_url = f"{CHADWICK_DATA_BASE_URL}/names.csv"
                names_resp = client.get(names_url)
                if names_resp.status_code == 200:
                    results["names.csv"] = names_resp.content
                    if self.cache_config.enabled:
                        with atomic_write(self.names_file) as part_path:
                            part_path.write_bytes(names_resp.content)

                # Download links.csv
                links_url = f"{CHADWICK_DATA_BASE_URL}/links.csv"
                links_resp = client.get(links_url)
                if links_resp.status_code == 200:
                    results["links.csv"] = links_resp.content
                    if self.cache_config.enabled:
                        with atomic_write(self.links_file) as part_path:
                            part_path.write_bytes(links_resp.content)

                if latest_sha:
                    self.manifest.set_completed(
                        "commit_sha",
                        records_count=len(results),
                        metadata={"sha": latest_sha},
                    )

                tracker.set_cache_hit(False)
                tracker.set_records(sum(len(b) for b in results.values()))
                return results

    async def extract_async(self, refresh: bool = False) -> dict[str, bytes]:
        """Asynchronously download all 16 shards and auxiliary files concurrently."""
        with default_audit_logger.track(
            operation="chadwick_extract_shards_async",
            source="chadwick",
            endpoint=CHADWICK_DATA_BASE_URL,
            destination=str(self.shards_dir),
        ) as tracker:
            if not refresh and self.are_shards_cached():
                tracker.set_cache_hit(True)
                return self._read_cached_files()

            semaphore = asyncio.Semaphore(self.rate_limit_config.max_concurrency)
            async with httpx.AsyncClient(timeout=self.rate_limit_config.timeout_seconds) as client:
                results: dict[str, bytes] = {}

                async def _fetch_file(filename: str, target_path: Path) -> None:
                    async with semaphore:
                        url = f"{CHADWICK_DATA_BASE_URL}/{filename}"
                        resp = await client.get(url)
                        if resp.status_code == 200:
                            content = resp.content
                            results[filename] = content
                            if self.cache_config.enabled:
                                with atomic_write(target_path) as part_path:
                                    part_path.write_bytes(content)

                tasks = [_fetch_file(shard, self.shards_dir / shard) for shard in HEX_SHARDS]
                tasks.append(_fetch_file("names.csv", self.names_file))
                tasks.append(_fetch_file("links.csv", self.links_file))
                await asyncio.gather(*tasks)

                tracker.set_cache_hit(False)
                return results

    def _read_cached_files(self) -> dict[str, bytes]:
        """Load all shard and auxiliary bytes from cache."""
        files: dict[str, bytes] = {}
        for shard in HEX_SHARDS:
            path = self.shards_dir / shard
            if path.exists():
                files[shard] = path.read_bytes()
        if self.names_file.exists():
            files["names.csv"] = self.names_file.read_bytes()
        if self.links_file.exists():
            files["links.csv"] = self.links_file.read_bytes()
        return files
