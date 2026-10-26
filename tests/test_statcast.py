"""Tests for Statcast (Baseball Savant) extraction, chunking, and normalization."""

from datetime import date
from pathlib import Path

import httpx
import pyarrow as pa
import pytest
import respx

from baseballpy.core.config import CacheConfig
from baseballpy.sources.statcast.extractor import (
    SAVANT_BASE_URL,
    StatcastExtractor,
    split_date_range,
)
from baseballpy.sources.statcast.normalizer import StatcastNormalizer

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "statcast" / "sample_pitches.csv"


def test_split_date_range() -> None:
    # 7-day range with chunk_days=5 -> 2 chunks
    ranges = split_date_range(date(2024, 4, 1), date(2024, 4, 7), chunk_days=5)
    assert len(ranges) == 2
    assert ranges[0] == (date(2024, 4, 1), date(2024, 4, 5))
    assert ranges[1] == (date(2024, 4, 6), date(2024, 4, 7))

    # Single day
    single = split_date_range(date(2024, 4, 1), date(2024, 4, 1), chunk_days=5)
    assert len(single) == 1
    assert single[0] == (date(2024, 4, 1), date(2024, 4, 1))

    # Invalid range raises ValueError
    with pytest.raises(ValueError, match="cannot be after"):
        split_date_range(date(2024, 4, 10), date(2024, 4, 1))


def test_statcast_normalizer_schema_and_types() -> None:
    normalizer = StatcastNormalizer()
    csv_bytes = FIXTURE_PATH.read_bytes()
    table = normalizer.normalize(csv_bytes)

    assert len(table) == 2

    # Check key columns and types
    assert table.schema.field("game_pk").type == pa.int32()
    assert table.schema.field("game_date").type == pa.date32()
    assert table.schema.field("release_speed").type == pa.float32()
    assert table.schema.field("at_bat_number").type == pa.int16()
    assert table.schema.field("pitch_number").type == pa.int16()

    # Bat tracking metrics (2024+)
    assert table.schema.field("bat_speed").type == pa.float32()
    assert table.schema.field("swing_length").type == pa.float32()

    # Dictionary-encoded types
    assert pa.types.is_dictionary(table.schema.field("pitch_type").type)
    assert pa.types.is_dictionary(table.schema.field("home_team").type)

    # Verify values
    pydict = table.to_pydict()
    assert pydict["player_name"] == ["Cole, Gerrit", "Cole, Gerrit"]
    assert pydict["release_speed"][0] == pytest.approx(98.2, rel=1e-2)
    assert pydict["bat_speed"][0] == pytest.approx(76.5, rel=1e-2)


def test_statcast_normalizer_preserves_new_columns() -> None:
    normalizer = StatcastNormalizer()
    # Add an unknown new column 'custom_metric'
    csv_text = "pitch_type,game_date,release_speed,custom_metric\nFF,2024-04-05,98.2,42.5\n"
    table = normalizer.normalize(csv_text)

    assert "custom_metric" in table.column_names
    assert len(table) == 1


@respx.mock
def test_statcast_extractor_mocked(tmp_path: Path) -> None:
    cache_config = CacheConfig(base_dir=tmp_path)
    extractor = StatcastExtractor(cache_config=cache_config, chunk_days=3)

    sample_csv = FIXTURE_PATH.read_bytes()
    respx.get(SAVANT_BASE_URL).mock(return_value=httpx.Response(200, content=sample_csv))

    table = extractor.extract(start_date="2024-04-01", end_date="2024-04-05")
    # 2 chunks requested: 04-01..04-03 and 04-04..04-05, each returning 2 rows
    assert len(table) == 4
    assert "game_pk" in table.column_names

    # Check cache directory contains parquet files
    cached_files = list(cache_config.statcast_dir.glob("*.parquet"))
    assert len(cached_files) == 2
