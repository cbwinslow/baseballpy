"""Configuration models for downloaders, cache managers, and sinks powered by Pydantic Settings."""

import os
import warnings
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from baseballpy.core.freshness import DEFAULT_TTLS, is_fresh

if TYPE_CHECKING:
    from baseballpy.core.atomic import ManifestTracker


def get_default_base_dir() -> Path:
    """Resolve default base directory with environment variable overrides."""
    if env_home := os.getenv("BASEBALLPY_HOME"):
        return Path(env_home).expanduser().resolve()
    if env_cache := os.getenv("BASEBALLPY_CACHE_DIR"):
        return Path(env_cache).expanduser().resolve().parent
    return (Path.home() / ".baseballpy").resolve()


LAYOUT_VERSION = 2

_LEGACY_ENV = {
    "enabled": "BASEBALLPY_CACHE_ENABLED",
    "ttl_seconds": "BASEBALLPY_CACHE_TTL_SECONDS",
}


class LakeConfig(BaseSettings):
    """Layout and freshness settings for the local data lake, loadable via BASEBALLPY_* env.

    Layout v2 (``$BASEBALLPY_HOME``): ``raw/``, ``processed/``, ``quarantine/``,
    ``cache/http/``, ``databases/baseball.duckdb``, ``logs/`` and a ``VERSION`` file.
    Path helpers never create directories; writers create them when they write.
    """

    model_config = SettingsConfigDict(
        env_prefix="BASEBALLPY_",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
    )

    home: Path = Field(
        default_factory=get_default_base_dir,
        description="Lake root (BASEBALLPY_HOME; default ~/.baseballpy)",
    )
    enabled: bool = Field(default=True, description="Whether persisting to the lake is enabled")
    ttl_seconds: int = Field(
        default=86400 * 30, description="Fallback time-to-live for mutable data in seconds"
    )
    ttl_overrides: dict[str, int | None] = Field(
        default_factory=dict,
        description="Per-dataset TTL seconds (None = immutable); keys match freshness.DEFAULT_TTLS",
    )
    today: date | None = Field(
        default=None, description="Override for 'today' (deterministic tests); None = real date"
    )
    raw_root_override: Path | None = Field(default=None, description="Override for raw/")
    processed_root_override: Path | None = Field(
        default=None, description="Override for processed/"
    )
    quarantine_root_override: Path | None = Field(
        default=None, description="Override for quarantine/"
    )
    http_cache_root_override: Path | None = Field(
        default=None, description="Override for cache/http/"
    )
    database_path_override: Path | None = Field(
        default=None, description="Override for databases/baseball.duckdb"
    )

    def __init__(self, **values: Any) -> None:
        """Build the config; ``base_dir=`` is accepted as a deprecated alias of ``home=``."""
        if "base_dir" in values:
            values.setdefault("home", values.pop("base_dir"))
        super().__init__(**values)

    @model_validator(mode="before")
    @classmethod
    def _legacy_inputs(cls, data: Any) -> Any:
        """Accept the pre-v2 BASEBALLPY_CACHE_* env vars (deprecated)."""
        if not isinstance(data, dict):
            return data
        values = dict(data)
        for field, env_name in _LEGACY_ENV.items():
            if field not in values and (raw := os.getenv(env_name)) is not None:
                warnings.warn(
                    f"{env_name} is deprecated; use BASEBALLPY_{field.upper()}",
                    DeprecationWarning,
                    stacklevel=2,
                )
                values[field] = raw
        return values

    @property
    def base_dir(self) -> Path:
        """Alias of ``home`` (kept for pre-v2 callers)."""
        return self.home

    @property
    def raw_root(self) -> Path:
        """Root of immutable upstream bytes."""
        return self.raw_root_override or (self.home / "raw")

    @property
    def processed_root(self) -> Path:
        """Root of typed Parquet datasets (the only tier DuckDB views read)."""
        return self.processed_root_override or (self.home / "processed")

    @property
    def quarantine_root(self) -> Path:
        """Root of dead-letter JSONL files."""
        return self.quarantine_root_override or (self.home / "quarantine")

    @property
    def http_cache_root(self) -> Path:
        """ETag/TTL bookkeeping only; always safe to delete."""
        return self.http_cache_root_override or (self.home / "cache" / "http")

    @property
    def database_path(self) -> Path:
        """Location of the DuckDB catalog (views only)."""
        return self.database_path_override or (self.home / "databases" / "baseball.duckdb")

    @property
    def version_file(self) -> Path:
        """Path of the layout ``VERSION`` file."""
        return self.home / "VERSION"

    def _dir(self, root: Path, source: str, dataset: str, season: int | None, create: bool) -> Path:
        path = root / source / dataset
        if season is not None:
            path = path / f"season={season}"
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def raw_dir(
        self, source: str, dataset: str, season: int | None = None, *, create: bool = False
    ) -> Path:
        """``raw/<source>/<dataset>/[season=YYYY/]`` (created only when ``create``)."""
        return self._dir(self.raw_root, source, dataset, season, create)

    def processed_dir(
        self, source: str, dataset: str, season: int | None = None, *, create: bool = False
    ) -> Path:
        """``processed/<source>/<dataset>/[season=YYYY/]`` (created only when ``create``)."""
        return self._dir(self.processed_root, source, dataset, season, create)

    def dataset_manifest(
        self, source: str, dataset: str, tier: Literal["raw", "processed"] = "processed"
    ) -> "ManifestTracker":
        """Manifest tracker stored at ``<tier>/<source>/<dataset>/manifest.json``."""
        from baseballpy.core.atomic import ManifestTracker

        root = self.raw_dir if tier == "raw" else self.processed_dir
        return ManifestTracker(root(source, dataset) / "manifest.json")

    def today_or_now(self) -> date:
        """The configured ``today`` or the real current date."""
        return self.today or date.today()

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


class CacheConfig(LakeConfig):
    """Deprecated alias of :class:`LakeConfig`; construct ``LakeConfig`` instead."""

    def __init__(self, **values: Any) -> None:
        """Warn about the deprecated name, then behave exactly like ``LakeConfig``."""
        warnings.warn(
            "CacheConfig is deprecated; use LakeConfig (layout v2)",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(**values)


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
        return self.log_dir_override or (self.base_dir / "logs")

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
        return self.quarantine_dir_override or (self.base_dir / "quarantine")


class PipelineConfig(BaseSettings):
    """Top-level pipeline configuration combining all subsystem settings."""

    model_config = SettingsConfigDict(
        env_prefix="BASEBALLPY_",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    lake: LakeConfig = Field(default_factory=LakeConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    quarantine: QuarantineConfig = Field(default_factory=QuarantineConfig)


@lru_cache(maxsize=1)
def get_config() -> PipelineConfig:
    """Return the lazily-built singleton PipelineConfig (call ``reset_config`` after env changes)."""
    return PipelineConfig()


def reset_config() -> None:
    """Drop the cached PipelineConfig so the next ``get_config()`` re-reads the environment."""
    get_config.cache_clear()
