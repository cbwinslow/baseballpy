"""Configuration models for downloaders, cache managers, and sinks powered by Pydantic Settings."""

import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from baseballpy.core.freshness import DEFAULT_TTLS, is_fresh


def get_default_base_dir() -> Path:
    """Resolve default base directory with environment variable overrides."""
    if env_home := os.getenv("BASEBALLPY_HOME"):
        return Path(env_home).expanduser().resolve()
    if env_cache := os.getenv("BASEBALLPY_CACHE_DIR"):
        return Path(env_cache).expanduser().resolve().parent
    return (Path.home() / ".baseballpy").resolve()


class CacheConfig(BaseSettings):
    """Cache configuration partitioned by data source, loadable via BASEBALLPY_CACHE_* env."""

    model_config = SettingsConfigDict(
        env_prefix="BASEBALLPY_CACHE_",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    base_dir: Path = Field(
        default_factory=get_default_base_dir,
        description="Root base directory for baseballpy data and cache",
    )
    enabled: bool = Field(default=True, description="Whether caching is enabled")
    ttl_seconds: int = Field(
        default=86400 * 30, description="Time-to-live for cached historical files in seconds"
    )

    ttl_overrides: dict[str, int | None] = Field(
        default_factory=dict,
        description="Per-dataset TTL seconds (None = immutable); keys match freshness.DEFAULT_TTLS",
    )
    today: date | None = Field(
        default=None, description="Override for 'today' (deterministic tests); None = real date"
    )

    statcast_dir_override: Path | None = Field(
        default=None, description="Explicit directory override for Statcast cache"
    )
    mlb_api_dir_override: Path | None = Field(
        default=None, description="Explicit directory override for MLB API cache"
    )
    retrosheet_dir_override: Path | None = Field(
        default=None, description="Explicit directory override for Retrosheet cache"
    )
    chadwick_dir_override: Path | None = Field(
        default=None, description="Explicit directory override for Chadwick cache"
    )
    lahman_dir_override: Path | None = Field(
        default=None, description="Explicit directory override for Lahman cache"
    )

    def ttl_for(self, dataset: str) -> int | None:
        """TTL seconds for a dataset family (None = immutable); falls back to ``ttl_seconds``."""
        if dataset in self.ttl_overrides:
            return self.ttl_overrides[dataset]
        if dataset in DEFAULT_TTLS:
            return DEFAULT_TTLS[dataset]
        return self.ttl_seconds

    def is_fresh(
        self,
        entry: dict[str, Any] | None,
        dataset: str,
        *,
        season: int | None = None,
        refresh: bool = False,
    ) -> bool:
        """Apply the freshness policy for ``dataset`` to a manifest ``entry``."""
        return is_fresh(
            entry,
            ttl_seconds=self.ttl_for(dataset),
            season=season,
            today=self.today,
            refresh=refresh,
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
        path = self.statcast_dir_override or (self.cache_root / "statcast")
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def mlb_api_dir(self) -> Path:
        """Partitioned cache directory for MLB Stats API."""
        path = self.mlb_api_dir_override or (self.cache_root / "mlb_api")
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def chadwick_dir(self) -> Path:
        """Partitioned cache directory for Chadwick Register."""
        path = self.chadwick_dir_override or (self.cache_root / "chadwick")
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def lahman_dir(self) -> Path:
        """Partitioned cache directory for Lahman database."""
        path = self.lahman_dir_override or (self.cache_root / "lahman")
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def retrosheet_dir(self) -> Path:
        """Partitioned cache directory for Retrosheet."""
        path = self.retrosheet_dir_override or (self.cache_root / "retrosheet")
        path.mkdir(parents=True, exist_ok=True)
        return path


class AuditConfig(BaseSettings):
    """Audit logging and telemetry configuration, loadable via BASEBALLPY_AUDIT_* env."""

    model_config = SettingsConfigDict(
        env_prefix="BASEBALLPY_AUDIT_",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    base_dir: Path = Field(
        default_factory=get_default_base_dir,
        description="Root base directory for logs",
    )
    enabled: bool = Field(default=True, description="Whether audit logging is enabled")
    log_dir_override: Path | None = Field(
        default=None, description="Explicit directory override for audit logs"
    )

    @property
    def log_dir(self) -> Path:
        """Directory for logs."""
        path = self.log_dir_override or (self.base_dir / "logs")
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def audit_file(self) -> Path:
        """Path to audit.jsonl telemetry file."""
        return self.log_dir / "audit.jsonl"


class RateLimitConfig(BaseSettings):
    """Rate limit, concurrency, and retry configuration for network extractors, loadable via BASEBALLPY_RATE_* env."""

    model_config = SettingsConfigDict(
        env_prefix="BASEBALLPY_RATE_",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    default_requests_per_second: float = Field(
        default=5.0, description="Default max outbound HTTP requests per second"
    )
    savant_rps: float = Field(
        default=2.5, description="Token bucket rate limit for baseballsavant.mlb.com"
    )
    statsapi_rps: float = Field(
        default=8.0, description="Token bucket rate limit for statsapi.mlb.com"
    )
    github_rps: float = Field(
        default=15.0, description="Token bucket rate limit for raw.githubusercontent.com"
    )
    host_rates: dict[str, float] = Field(
        default_factory=dict,
        description="Host-specific token bucket rate limits in requests per second",
    )
    max_concurrency: int = Field(
        default=4, description="Maximum number of simultaneous concurrent outbound requests"
    )
    max_retries: int = Field(default=5, description="Maximum retry attempts on 429/5xx errors")
    backoff_factor: float = Field(default=1.5, description="Exponential backoff factor")
    timeout_seconds: float = Field(default=30.0, description="HTTP request timeout in seconds")

    @model_validator(mode="after")
    def populate_host_rates(self) -> "RateLimitConfig":
        """Merge host-specific defaults if not explicitly provided."""
        defaults = {
            "baseballsavant.mlb.com": self.savant_rps,
            "statsapi.mlb.com": self.statsapi_rps,
            "raw.githubusercontent.com": self.github_rps,
        }
        for host, rate in defaults.items():
            if host not in self.host_rates:
                self.host_rates[host] = rate
        return self


class StreamingConfig(BaseSettings):
    """Configuration for real-time live game event streaming, loadable via BASEBALLPY_STREAM_* env."""

    model_config = SettingsConfigDict(
        env_prefix="BASEBALLPY_STREAM_",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    poll_interval_seconds: float = Field(
        default=5.0, description="Interval in seconds between polling live game feeds"
    )
    max_inactivity_minutes: int = Field(
        default=60, description="Timeout in minutes after which inactive games cease polling"
    )
    enable_conditional_etag: bool = Field(
        default=True, description="Whether to send If-None-Match ETag headers to minimize bandwidth"
    )


class QuarantineConfig(BaseSettings):
    """Configuration for dead-letter quarantine of corrupted records, loadable via BASEBALLPY_QUARANTINE_* env."""

    model_config = SettingsConfigDict(
        env_prefix="BASEBALLPY_QUARANTINE_",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    base_dir: Path = Field(
        default_factory=get_default_base_dir,
        description="Root base directory for quarantine",
    )
    enabled: bool = Field(default=True, description="Whether to capture unparseable records")
    quarantine_dir_override: Path | None = Field(
        default=None, description="Explicit directory override for quarantine"
    )

    @property
    def quarantine_dir(self) -> Path:
        """Directory for persisting unparseable or malformed payloads."""
        path = self.quarantine_dir_override or (self.base_dir / "quarantine")
        path.mkdir(parents=True, exist_ok=True)
        return path


class PipelineConfig(BaseSettings):
    """Top-level pipeline configuration combining all subsystem settings."""

    model_config = SettingsConfigDict(
        env_prefix="BASEBALLPY_",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    cache: CacheConfig = Field(default_factory=CacheConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    quarantine: QuarantineConfig = Field(default_factory=QuarantineConfig)


@lru_cache(maxsize=1)
def get_config() -> PipelineConfig:
    """Return singleton PipelineConfig instance."""
    return PipelineConfig()
