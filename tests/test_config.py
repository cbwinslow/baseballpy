"""Tests for configuration models, directory layout, environment variable overrides, and path resolution."""

import os
from pathlib import Path
from unittest import mock

import pytest

from baseballpy.core.config import (
    AuditConfig,
    CacheConfig,
    LakeConfig,
    PipelineConfig,
    QuarantineConfig,
    RateLimitConfig,
    StreamingConfig,
    get_config,
    reset_config,
)


def test_lake_config_layout_v2(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    assert config.raw_root == tmp_path / "raw"
    assert config.processed_root == tmp_path / "processed"
    assert config.quarantine_root == tmp_path / "quarantine"
    assert config.http_cache_root == tmp_path / "cache" / "http"
    assert config.database_path == tmp_path / "databases" / "baseball.duckdb"
    assert config.version_file == tmp_path / "VERSION"
    assert config.raw_dir("statcast", "pitches", 2024) == (
        tmp_path / "raw" / "statcast" / "pitches" / "season=2024"
    )
    assert config.processed_dir("lahman", "People") == tmp_path / "processed" / "lahman" / "People"


def test_lake_config_never_creates_directories_on_read(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path / "lake")
    _ = (
        config.raw_root,
        config.processed_root,
        config.quarantine_root,
        config.http_cache_root,
        config.database_path,
        config.raw_dir("statcast", "pitches", 2024),
        config.processed_dir("statcast", "pitches", 2024),
        AuditConfig(base_dir=tmp_path / "lake").log_dir,
        QuarantineConfig(base_dir=tmp_path / "lake").quarantine_dir,
    )
    assert not (tmp_path / "lake").exists()
    created = config.raw_dir("statcast", "pitches", 2024, create=True)
    assert created.is_dir()


def test_lake_config_explicit_overrides(tmp_path: Path) -> None:
    config = LakeConfig(
        home=tmp_path,
        raw_root_override=tmp_path / "r",
        processed_root_override=tmp_path / "p",
        database_path_override=tmp_path / "x.duckdb",
    )
    assert config.raw_root == tmp_path / "r"
    assert config.processed_dir("retrosheet", "events", 2023) == (
        tmp_path / "p" / "retrosheet" / "events" / "season=2023"
    )
    assert config.database_path == tmp_path / "x.duckdb"


def test_lake_config_env_vars(tmp_path: Path) -> None:
    with mock.patch.dict(
        os.environ,
        {
            "BASEBALLPY_HOME": str(tmp_path),
            "BASEBALLPY_ENABLED": "false",
            "BASEBALLPY_TTL_SECONDS": "3600",
            "BASEBALLPY_PROCESSED_ROOT_OVERRIDE": str(tmp_path / "elsewhere"),
        },
    ):
        config = LakeConfig()
        assert config.home == tmp_path.resolve()
        assert config.enabled is False
        assert config.ttl_seconds == 3600
        assert config.processed_root == tmp_path / "elsewhere"


def test_lake_config_legacy_cache_env_warns(tmp_path: Path) -> None:
    with (
        mock.patch.dict(
            os.environ,
            {"BASEBALLPY_CACHE_TTL_SECONDS": "77", "BASEBALLPY_HOME": str(tmp_path)},
        ),
        pytest.warns(DeprecationWarning, match="BASEBALLPY_CACHE_TTL_SECONDS"),
    ):
        config = LakeConfig()
    assert config.ttl_seconds == 77


def test_legacy_cache_dir_env_still_resolves_home(tmp_path: Path) -> None:
    with mock.patch.dict(
        os.environ, {"BASEBALLPY_CACHE_DIR": str(tmp_path / "cache")}, clear=False
    ):
        os.environ.pop("BASEBALLPY_HOME", None)
        assert LakeConfig().home == tmp_path.resolve()


def test_cache_config_is_a_deprecated_alias(tmp_path: Path) -> None:
    with pytest.warns(DeprecationWarning, match="CacheConfig is deprecated"):
        config = CacheConfig(base_dir=tmp_path)
    assert isinstance(config, LakeConfig)
    assert config.home == tmp_path


def test_dataset_manifest_location(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    manifest = config.dataset_manifest("retrosheet", "events", "raw")
    manifest.set_completed("season=2023/x", records_count=1)
    assert (tmp_path / "raw" / "retrosheet" / "events" / "manifest.json").exists()
    assert config.dataset_manifest("retrosheet", "events").is_completed("season=2023/x") is False


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

    quarantine_cfg = QuarantineConfig(base_dir=tmp_path)
    assert quarantine_cfg.quarantine_dir == tmp_path / "quarantine"


def test_streaming_config() -> None:
    stream_cfg = StreamingConfig(poll_interval_seconds=2.0)
    assert stream_cfg.poll_interval_seconds == 2.0
    assert stream_cfg.enable_conditional_etag is True


def test_pipeline_config_custom_base(tmp_path: Path) -> None:
    pipeline = PipelineConfig(
        lake=LakeConfig(home=tmp_path),
    )
    assert pipeline.lake.home == tmp_path
    assert pipeline.rate_limit.max_concurrency == 4
    assert pipeline.rate_limit.host_rates["statsapi.mlb.com"] == 8.0


def test_get_config_singleton() -> None:
    cfg1 = get_config()
    cfg2 = get_config()
    assert cfg1 is cfg2


def test_dotenv_in_cwd_is_not_read_implicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("BASEBALLPY_RATE_MAX_CONCURRENCY=7\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BASEBALLPY_RATE_MAX_CONCURRENCY", raising=False)
    monkeypatch.delenv("BASEBALLPY_ENV_FILE", raising=False)
    assert RateLimitConfig().max_concurrency != 7


def test_env_file_var_opts_in_and_real_env_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / "custom.env"
    env_file.write_text(
        "BASEBALLPY_RATE_MAX_CONCURRENCY=7\nBASEBALLPY_STREAM_POLL_INTERVAL_SECONDS=2.5\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BASEBALLPY_ENV_FILE", str(env_file))
    monkeypatch.delenv("BASEBALLPY_RATE_MAX_CONCURRENCY", raising=False)
    monkeypatch.delenv("BASEBALLPY_STREAM_POLL_INTERVAL_SECONDS", raising=False)
    assert RateLimitConfig().max_concurrency == 7
    monkeypatch.setenv("BASEBALLPY_RATE_MAX_CONCURRENCY", "3")
    assert RateLimitConfig().max_concurrency == 3
    assert StreamingConfig().poll_interval_seconds == 2.5


def test_reset_config_rereads_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path / "a"))
    reset_config()
    assert get_config().lake.home == (tmp_path / "a").resolve()
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path / "b"))
    assert get_config().lake.home == (tmp_path / "a").resolve()
    reset_config()
    assert get_config().lake.home == (tmp_path / "b").resolve()
    reset_config()
