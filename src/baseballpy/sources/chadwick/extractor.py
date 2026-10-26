"""Extractor for the Chadwick Bureau Register from GitHub."""

from pathlib import Path

import httpx

from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import CacheConfig, RateLimitConfig

CHADWICK_PEOPLE_URL = (
    "https://raw.githubusercontent.com/chadwickbureau/register/master/data/people.csv"
)


class ChadwickExtractor:
    """Extracts the Chadwick Bureau Player Register with local caching and ETag validation."""

    def __init__(
        self,
        cache_config: CacheConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ) -> None:
        self.cache_config = cache_config or CacheConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.url = CHADWICK_PEOPLE_URL

    @property
    def cache_file(self) -> Path:
        """Local path for cached Chadwick people CSV."""
        return self.cache_config.chadwick_dir / "people.csv"

    @property
    def etag_file(self) -> Path:
        """Local path for stored ETag metadata."""
        return self.cache_config.chadwick_dir / "people.etag"

    def extract(self, refresh: bool = False) -> bytes:
        """Synchronously download Chadwick people.csv or return cached content."""
        with default_audit_logger.track(
            operation="chadwick_extract",
            source="chadwick",
            endpoint=self.url,
            destination=str(self.cache_file),
        ) as tracker:
            # Check local cache first if refresh not requested
            if not refresh and self.cache_file.exists():
                tracker.set_cache_hit(True)
                content = self.cache_file.read_bytes()
                tracker.set_records(content.count(b"\n"))
                return content

            # Conditional request with ETag
            headers = {}
            if self.etag_file.exists() and not refresh:
                headers["If-None-Match"] = self.etag_file.read_text().strip()

            with httpx.Client(timeout=self.rate_limit_config.timeout_seconds) as client:
                response = client.get(self.url, headers=headers)

                if response.status_code == 304 and self.cache_file.exists():
                    tracker.set_cache_hit(True)
                    content = self.cache_file.read_bytes()
                    tracker.set_records(content.count(b"\n"))
                    return content

                response.raise_for_status()
                content = response.content

                # Save content and ETag to cache
                if self.cache_config.enabled:
                    self.cache_file.write_bytes(content)
                    if etag := response.headers.get("ETag"):
                        self.etag_file.write_text(etag)

                tracker.set_cache_hit(False)
                tracker.set_records(content.count(b"\n"))
                return content

    async def extract_async(self, refresh: bool = False) -> bytes:
        """Asynchronously download Chadwick people.csv or return cached content."""
        with default_audit_logger.track(
            operation="chadwick_extract_async",
            source="chadwick",
            endpoint=self.url,
            destination=str(self.cache_file),
        ) as tracker:
            if not refresh and self.cache_file.exists():
                tracker.set_cache_hit(True)
                content = self.cache_file.read_bytes()
                tracker.set_records(content.count(b"\n"))
                return content

            headers = {}
            if self.etag_file.exists() and not refresh:
                headers["If-None-Match"] = self.etag_file.read_text().strip()

            async with httpx.AsyncClient(timeout=self.rate_limit_config.timeout_seconds) as client:
                response = await client.get(self.url, headers=headers)

                if response.status_code == 304 and self.cache_file.exists():
                    tracker.set_cache_hit(True)
                    content = self.cache_file.read_bytes()
                    tracker.set_records(content.count(b"\n"))
                    return content

                response.raise_for_status()
                content = response.content

                if self.cache_config.enabled:
                    self.cache_file.write_bytes(content)
                    if etag := response.headers.get("ETag"):
                        self.etag_file.write_text(etag)

                tracker.set_cache_hit(False)
                tracker.set_records(content.count(b"\n"))
                return content
