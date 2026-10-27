"""Comprehensive production smoke test suite for baseballpy.

Tests multi-season downloads, chunking, manifest checkpointing, zero-loss
idempotency, atomic download gate guarantees, and cross-source sink pipelines.
"""

from pathlib import Path

import duckdb
import httpx
import polars as pl
import pytest
import respx

from baseballpy.core.atomic import atomic_write
from baseballpy.core.config import CacheConfig
from baseballpy.sinks.duckdb import DuckDBSink
from baseballpy.sinks.polars import PolarsSink
from baseballpy.sources.mlb_api.api import MlbApiSource
from baseballpy.sources.retrosheet.api import RetrosheetSource
from baseballpy.sources.retrosheet.downloader import GITHUB_RETROSHEET_BASE
from baseballpy.sources.statcast.extractor import (
    SAVANT_BASE_URL,
    StatcastExtractor,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "statcast" / "sample_pitches.csv"


@respx.mock
def test_smoke_retrosheet_multi_season_and_idempotency(tmp_path: Path) -> None:
    """Stress test multi-season Retrosheet download, Chadwick parsing, and zero-loss cache hits."""
    cache_config = CacheConfig(base_dir=tmp_path)
    source = RetrosheetSource(cache_config=cache_config)

    # 1. Setup mock files for seasons 2022 and 2023
    for year in (2022, 2023):
        team_manifest = b"BOS,A\n"
        fake_eva = (
            f"id,BOS{year}04010\n"
            f"info,date,{year}/04/01\n"
            f"info,hometeam,BOS\n"
            f"info,visteam,BAL\n"
            f"start,play01,Batter One,0,1,4\n"
            f"start,pitch01,Pitcher One,1,1,1\n"
            f"play,1,0,play01,00,,S\n"
            f"data,er,pitch01,0\n"
        ).encode()
        fake_ros = b"play01,One,Batter,R,R,BOS,OF\n"

        respx.get(f"{GITHUB_RETROSHEET_BASE}/seasons/{year}/TEAM{year}").mock(
            return_value=httpx.Response(200, content=team_manifest)
        )
        respx.get(f"{GITHUB_RETROSHEET_BASE}/seasons/{year}/{year}BOS.EVA").mock(
            return_value=httpx.Response(200, content=fake_eva)
        )
        respx.get(f"{GITHUB_RETROSHEET_BASE}/seasons/{year}/BOS{year}.ROS").mock(
            return_value=httpx.Response(200, content=fake_ros)
        )

    # 2. Extract events across both seasons
    events_2022 = source.events(2022)
    events_2023 = source.events(2023)

    assert len(events_2022) == 1
    assert len(events_2023) == 1
    assert events_2022["GAME_ID"].to_pylist() == ["BOS202204010"]
    assert events_2023["GAME_ID"].to_pylist() == ["BOS202304010"]

    # 3. Check filesystem separation
    raw_2022 = cache_config.retrosheet_dir / "raw" / "2022"
    raw_2023 = cache_config.retrosheet_dir / "raw" / "2023"
    proc_2022 = cache_config.retrosheet_dir / "processed" / "events" / "season=2022"
    proc_2023 = cache_config.retrosheet_dir / "processed" / "events" / "season=2023"

    assert (raw_2022 / "2022BOS.EVA").exists()
    assert (raw_2023 / "2023BOS.EVA").exists()
    assert (proc_2022 / "events.parquet").exists()
    assert (proc_2023 / "events.parquet").exists()

    # 4. Boxscores across both seasons
    bat_22, pitch_22 = source.boxscores(2022)
    bat_23, pitch_23 = source.boxscores(2023)
    assert len(bat_22) > 0 and len(pitch_22) > 0
    assert len(bat_23) > 0 and len(pitch_23) > 0

    # 5. Check manifest checkpoint status
    assert source.manifest.is_completed("events_2022")
    assert source.manifest.is_completed("events_2023")
    assert source.manifest.is_completed("box_batting_2022")
    assert source.manifest.is_completed("box_pitching_2023")

    # 6. Idempotency test: Invalidate network endpoints to fail with HTTP 500
    respx.get(f"{GITHUB_RETROSHEET_BASE}/seasons/2022/TEAM2022").mock(
        return_value=httpx.Response(500)
    )
    respx.get(f"{GITHUB_RETROSHEET_BASE}/seasons/2023/TEAM2023").mock(
        return_value=httpx.Response(500)
    )

    # Must cleanly load directly from Parquet cache without raising errors
    cached_22 = source.events(2022, refresh=False)
    cached_23 = source.events(2023, refresh=False)
    assert len(cached_22) == 1
    assert len(cached_23) == 1
    assert cached_22["GAME_ID"].to_pylist() == ["BOS202204010"]


@respx.mock
def test_smoke_statcast_multi_chunk_idempotency_and_manifest(tmp_path: Path) -> None:
    """Stress test Statcast 15-day range split into three 5-day chunks with manifest tracking."""
    cache_config = CacheConfig(base_dir=tmp_path)
    extractor = StatcastExtractor(cache_config=cache_config, chunk_days=5)

    sample_csv = FIXTURE_PATH.read_bytes()
    # Mock savant search endpoint
    search_route = respx.get(SAVANT_BASE_URL).mock(
        return_value=httpx.Response(200, content=sample_csv)
    )

    # 15 days: 2024-04-01 to 2024-04-15 -> 3 chunks (04-01..05, 04-06..10, 04-11..15)
    table = extractor.extract(start_date="2024-04-01", end_date="2024-04-15")

    # Each chunk fixture has 2 rows -> total 6 rows
    assert len(table) == 6
    assert search_route.call_count == 3

    # Check that exactly 3 parquet files exist in cache (season=2024/ partition)
    parquet_files = sorted(list(cache_config.statcast_dir.glob("**/*.parquet")))
    assert len(parquet_files) == 3

    # Check manifest records all 3 chunks
    for chunk_file in parquet_files:
        chunk_name = chunk_file.stem
        assert extractor.manifest.is_completed(chunk_name)

    # Test idempotency: Mock route to return 500 error to ensure network is not touched
    search_route.mock(return_value=httpx.Response(500))

    cached_table = extractor.extract(start_date="2024-04-01", end_date="2024-04-15")
    assert len(cached_table) == 6
    # Call count should not have increased
    assert search_route.call_count == 3


def test_smoke_atomic_gate_and_error_recovery(tmp_path: Path) -> None:
    """Validate two-phase atomic write gate protects against partial or corrupted writes."""
    final_file = tmp_path / "protected" / "critical_dataset.parquet"

    # 1. Simulate an interrupted download
    part_path: Path | None = None
    with (
        pytest.raises(RuntimeError, match="Network connection severed"),
        atomic_write(final_file) as temp_target,
    ):
        part_path = temp_target
        assert str(temp_target).endswith(".part")
        temp_target.parent.mkdir(parents=True, exist_ok=True)
        temp_target.write_bytes(b"corrupted partial data")
        raise RuntimeError("Network connection severed mid-stream")

    # Ensure final file was NEVER created
    assert not final_file.exists()
    # Ensure temporary .part file was safely removed on error exit
    assert part_path is not None
    assert not part_path.exists()

    # 2. Simulate successful retry
    with atomic_write(final_file) as temp_target:
        temp_target.write_bytes(b"valid payload")

    # Final file must now exist atomically
    assert final_file.exists()
    assert final_file.read_bytes() == b"valid payload"


@respx.mock
def test_smoke_cross_source_duckdb_and_polars_pipeline(tmp_path: Path) -> None:
    """Stress test pipeline writing Statcast & MLB API data to DuckDB and Polars sinks."""
    cache_config = CacheConfig(base_dir=tmp_path)

    # 1. Statcast data
    statcast_extractor = StatcastExtractor(cache_config=cache_config, chunk_days=5)
    sample_pitches = FIXTURE_PATH.read_bytes()
    respx.get(SAVANT_BASE_URL).mock(return_value=httpx.Response(200, content=sample_pitches))
    pitches_table = statcast_extractor.extract(start_date="2024-04-01", end_date="2024-04-05")
    assert len(pitches_table) == 2

    # 2. MLB Stats API Schedule data
    mlb_source = MlbApiSource(cache_config=cache_config)
    sample_sched_json = {
        "dates": [
            {
                "date": "2024-04-01",
                "games": [
                    {
                        "gamePk": 745300,
                        "gameType": "R",
                        "season": "2024",
                        "status": {
                            "abstractGameState": "Final",
                            "codedGameState": "F",
                            "detailedState": "Final",
                        },
                        "teams": {
                            "away": {
                                "team": {"id": 110, "name": "Baltimore Orioles"},
                                "score": 4,
                                "isWinner": True,
                            },
                            "home": {
                                "team": {"id": 111, "name": "Boston Red Sox"},
                                "score": 2,
                                "isWinner": False,
                            },
                        },
                        "venue": {"id": 3, "name": "Fenway Park"},
                    }
                ],
            }
        ]
    }
    respx.get("https://statsapi.mlb.com/api/v1/schedule").mock(
        return_value=httpx.Response(200, json=sample_sched_json)
    )
    schedule_table = mlb_source.schedule(start_date="2024-04-01", end_date="2024-04-01")
    assert len(schedule_table) == 1

    # 3. Ingest both into shared DuckDB database
    duck_db_path = str(tmp_path / "baseball_warehouse.duckdb")
    duck_sink = DuckDBSink()
    duck_sink.write(pitches_table, destination=duck_db_path, table_name="statcast_pitches")
    duck_sink.write(schedule_table, destination=duck_db_path, table_name="mlb_schedule")

    # Verify query in DuckDB
    con = duckdb.connect(duck_db_path)
    pitch_cnt = con.execute("SELECT count(*) FROM statcast_pitches").fetchone()[0]  # type: ignore[index]
    game_cnt = con.execute("SELECT count(*) FROM mlb_schedule").fetchone()[0]  # type: ignore[index]
    assert pitch_cnt == 2
    assert game_cnt == 1

    # Verify DuckDB cross-table query
    con.close()

    # 4. Ingest into PolarsSink and perform aggregations
    polars_sink = PolarsSink()
    assert polars_sink.write(pitches_table, destination="statcast_pitches") == 2
    pl_df = polars_sink.last
    assert isinstance(pl_df, pl.DataFrame)
    assert pl_df.shape[0] == 2
    avg_speed = pl_df.select(pl.col("release_speed").mean()).item()
    assert avg_speed > 90.0
