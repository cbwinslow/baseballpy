"""Tests for configuration models, directory layout, environment variable overrides, and path resolution."""

import os
from pathlib import Path
from unittest import mock

from baseballpy.core.config import (
    AuditConfig,
    CacheConfig,
    PipelineConfig,
    QuarantineConfig,
    RateLimitConfig,
    StreamingConfig,
    get_config,
)


def test_cache_config_default_partitioning(tmp_path: Path) -> None:
    config = CacheConfig(base_dir=tmp_path)
    assert config.cache_root == tmp_path / "cache"
    assert config.statcast_dir == tmp_path / "cache" / "statcast"
    assert config.mlb_api_dir == tmp_path / "cache" / "mlb_api"
    assert config.chadwick_dir == tmp_path / "cache" / "chadwick"
    assert config.lahman_dir == tmp_path / "cache" / "lahman"
    assert config.retrosheet_dir == tmp_path / "cache" / "retrosheet"

    # Verify directories are created
    assert config.statcast_dir.exists()
    assert config.mlb_api_dir.exists()
    assert config.chadwick_dir.exists()


def test_cache_config_explicit_directory_overrides(tmp_path: Path) -> None:
    custom_statcast = tmp_path / "custom_statcast"
    custom_retrosheet = tmp_path / "custom_retro"
    config = CacheConfig(
        base_dir=tmp_path,
        statcast_dir_override=custom_statcast,
        retrosheet_dir_override=custom_retrosheet,
    )
    assert config.statcast_dir == custom_statcast
    assert config.retrosheet_dir == custom_retrosheet
    assert custom_statcast.exists()
    assert custom_retrosheet.exists()


def test_cache_config_env_vars(tmp_path: Path) -> None:
    custom_dir = tmp_path / "env_statcast"
    with mock.patch.dict(
        os.environ,
        {
            "BASEBALLPY_CACHE_ENABLED": "false",
            "BASEBALLPY_CACHE_TTL_SECONDS": "3600",
            "BASEBALLPY_CACHE_STATCAST_DIR_OVERRIDE": str(custom_dir),
        },
    ):
        config = CacheConfig()
        assert config.enabled is False
        assert config.ttl_seconds == 3600
        assert config.statcast_dir == custom_dir
        assert custom_dir.exists()


def test_rate_limit_config_env_vars() -> None:
    with mock.patch.dict(
        os.environ,
        {
            "BASEBALLPY_RATE_MAX_CONCURRENCY": "8",
            "BASEBALLPY_RATE_TIMEOUT_SECONDS": "45.0",
            "BASEBALLPY_RATE_SAVANT_RPS": "1.5",
        },
    ):
        rate_cfg = RateLimitConfig()
        assert rate_cfg.max_concurrency == 8
        assert rate_cfg.timeout_seconds == 45.0
        assert rate_cfg.savant_rps == 1.5
        assert rate_cfg.host_rates["baseballsavant.mlb.com"] == 1.5
        assert rate_cfg.host_rates["statsapi.mlb.com"] == 8.0


def test_audit_and_quarantine_config(tmp_path: Path) -> None:
    audit_cfg = AuditConfig(base_dir=tmp_path)
    assert audit_cfg.log_dir == tmp_path / "logs"
    assert audit_cfg.audit_file == tmp_path / "logs" / "audit.jsonl"
    assert audit_cfg.log_dir.exists()

    quarantine_cfg = QuarantineConfig(base_dir=tmp_path)
    assert quarantine_cfg.quarantine_dir == tmp_path / "quarantine"
    assert quarantine_cfg.quarantine_dir.exists()


def test_streaming_config() -> None:
    stream_cfg = StreamingConfig(poll_interval_seconds=2.0)
    assert stream_cfg.poll_interval_seconds == 2.0
    assert stream_cfg.enable_conditional_etag is True


def test_pipeline_config_custom_base(tmp_path: Path) -> None:
    pipeline = PipelineConfig(
        cache=CacheConfig(base_dir=tmp_path),
    )
    assert pipeline.cache.base_dir == tmp_path
    assert pipeline.rate_limit.max_concurrency == 4
    assert pipeline.rate_limit.host_rates["statsapi.mlb.com"] == 8.0


def test_get_config_singleton() -> None:
    cfg1 = get_config()
    cfg2 = get_config()
    assert cfg1 is cfg2
