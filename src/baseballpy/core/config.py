"""Configuration models for downloaders, cache managers, and sinks."""

import os
from pathlib import Path

from pydantic import BaseModel, Field


def get_default_base_dir() -> Path:
    """Resolve default base directory with environment variable overrides."""
    if env_home := os.getenv("BASEBALLPY_HOME"):
        return Path(env_home).expanduser().resolve()
    if env_cache := os.getenv("BASEBALLPY_CACHE_DIR"):
        return Path(env_cache).expanduser().resolve().parent
    return (Path.home() / ".baseballpy").resolve()


class CacheConfig(BaseModel):
    """Cache configuration partitioned by data source."""

    base_dir: Path = Field(
        default_factory=get_default_base_dir,
        description="Root base directory for baseballpy data and cache",
    )
    enabled: bool = Field(default=True, description="Whether caching is enabled")
    ttl_seconds: int = Field(
        default=86400 * 30, description="Time-to-live for cached historical files"
    )

    @property
    def cache_root(self) -> Path:
        """Root directory for cached downloads."""
        path = self.base_dir / "cache"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def statcast_dir(self) -> Path:
        """Partitioned cache directory for Statcast."""
        path = self.cache_root / "statcast"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def mlb_api_dir(self) -> Path:
        """Partitioned cache directory for MLB Stats API."""
        path = self.cache_root / "mlb_api"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def chadwick_dir(self) -> Path:
        """Partitioned cache directory for Chadwick Register."""
        path = self.cache_root / "chadwick"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def lahman_dir(self) -> Path:
        """Partitioned cache directory for Lahman database."""
        path = self.cache_root / "lahman"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def retrosheet_dir(self) -> Path:
        """Partitioned cache directory for Retrosheet."""
        path = self.cache_root / "retrosheet"
        path.mkdir(parents=True, exist_ok=True)
        return path


class AuditConfig(BaseModel):
    """Audit logging and telemetry configuration."""

    base_dir: Path = Field(
        default_factory=get_default_base_dir,
        description="Root base directory",
    )
    enabled: bool = Field(default=True, description="Whether audit logging is enabled")

    @property
    def log_dir(self) -> Path:
        """Directory for logs."""
        path = self.base_dir / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def audit_file(self) -> Path:
        """Path to audit.jsonl telemetry file."""
        return self.log_dir / "audit.jsonl"


class RateLimitConfig(BaseModel):
    """Rate limit, concurrency, and retry configuration for network extractors."""

    default_requests_per_second: float = Field(
        default=5.0, description="Default max outbound HTTP requests per second"
    )
    host_rates: dict[str, float] = Field(
        default_factory=lambda: {
            "baseballsavant.mlb.com": 2.5,
            "statsapi.mlb.com": 8.0,
            "raw.githubusercontent.com": 15.0,
        },
        description="Host-specific token bucket rate limits in requests per second",
    )
    max_concurrency: int = Field(
        default=4, description="Maximum number of simultaneous concurrent outbound requests"
    )
    max_retries: int = Field(default=5, description="Maximum retry attempts on 429/5xx errors")
    backoff_factor: float = Field(default=1.5, description="Exponential backoff factor")
    timeout_seconds: float = Field(default=30.0, description="HTTP request timeout in seconds")


class StreamingConfig(BaseModel):
    """Configuration for real-time live game event streaming."""

    poll_interval_seconds: float = Field(
        default=5.0, description="Interval in seconds between polling live game feeds"
    )
    max_inactivity_minutes: int = Field(
        default=60, description="Timeout in minutes after which inactive games cease polling"
    )
    enable_conditional_etag: bool = Field(
        default=True, description="Whether to send If-None-Match ETag headers to minimize bandwidth"
    )


class QuarantineConfig(BaseModel):
    """Configuration for dead-letter quarantine of corrupted or unparseable records."""

    base_dir: Path = Field(
        default_factory=get_default_base_dir,
        description="Root base directory",
    )
    enabled: bool = Field(default=True, description="Whether to capture unparseable records")

    @property
    def quarantine_dir(self) -> Path:
        """Directory for persisting unparseable or malformed payloads."""
        path = self.base_dir / "quarantine"
        path.mkdir(parents=True, exist_ok=True)
        return path


class PipelineConfig(BaseModel):
    """Top-level pipeline configuration."""

    cache: CacheConfig = Field(default_factory=CacheConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    quarantine: QuarantineConfig = Field(default_factory=QuarantineConfig)
