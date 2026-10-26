"""Tests for configuration models, directory layout, and path resolution."""

from pathlib import Path

from baseballpy.core.config import CacheConfig, PipelineConfig


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


def test_pipeline_config_custom_base(tmp_path: Path) -> None:
    pipeline = PipelineConfig(
        cache=CacheConfig(base_dir=tmp_path),
    )
    assert pipeline.cache.base_dir == tmp_path
    assert pipeline.rate_limit.max_concurrency == 4
    assert pipeline.rate_limit.host_rates["statsapi.mlb.com"] == 8.0
