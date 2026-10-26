"""Tests for SABR Lahman Baseball Database extraction, normalization, and local archive import."""

import zipfile
from pathlib import Path

import httpx
import pyarrow as pa
import respx

from baseballpy.core.config import CacheConfig
from baseballpy.sources.lahman.api import LahmanSource
from baseballpy.sources.lahman.extractor import LAHMAN_GITHUB_BASE
from baseballpy.sources.lahman.normalizer import LahmanNormalizer
from baseballpy.sources.lahman.schema import LahmanTable

SAMPLE_PEOPLE_CSV = (
    "playerID,birthYear,birthMonth,birthDay,birthCountry,birthState,birthCity,deathYear,deathMonth,deathDay,deathCountry,deathState,deathCity,nameFirst,nameLast,nameGiven,weight,height,bats,throws,debut,finalGame,retroID,bbrefID\n"
    "aardsda01,1981,12,27,USA,CO,Denver,,,,,,,David,Aardsma,David Allan,215,75,R,R,2004-04-06,2015-08-23,aardd001,aardsda01\n"
    "ohtansh01,1994,7,5,Japan,Iwate,Oshu,,,,,,,Shohei,Ohtani,Shohei,210,76,L,R,2018-03-29,2025-10-01,ohtas001,ohtansh01\n"
)

SAMPLE_BATTING_CSV = (
    "playerID,yearID,stint,teamID,lgID,G,AB,R,H,2B,3B,HR,RBI,SB,CS,BB,SO,IBB,HBP,SH,SF,GIDP\n"
    "ohtansh01,2024,1,LAD,NL,159,636,134,197,38,7,54,130,59,4,81,162,20,6,0,5,5\n"
    "judgaa01,2024,1,NYA,AL,158,559,122,180,36,1,58,144,10,0,133,171,20,9,0,4,22\n"
)


def test_lahman_normalizer_people() -> None:
    normalizer = LahmanNormalizer()
    table = normalizer.normalize(SAMPLE_PEOPLE_CSV, table_name=LahmanTable.PEOPLE)

    assert len(table) == 2
    assert "playerID" in table.column_names
    assert "nameFirst" in table.column_names
    assert table["playerID"].to_pylist() == ["aardsda01", "ohtansh01"]
    assert table["birthYear"].to_pylist() == [1981, 1994]
    assert pa.types.is_date32(table.schema.field("debut").type)


def test_lahman_normalizer_batting() -> None:
    normalizer = LahmanNormalizer()
    table = normalizer.normalize(SAMPLE_BATTING_CSV, table_name=LahmanTable.BATTING)

    assert len(table) == 2
    assert table["playerID"].to_pylist() == ["ohtansh01", "judgaa01"]
    assert table["HR"].to_pylist() == [54, 58]
    assert table["SB"].to_pylist() == [59, 10]
    assert pa.types.is_int16(table.schema.field("HR").type)


@respx.mock
def test_lahman_extractor_and_caching(tmp_path: Path) -> None:
    cache_config = CacheConfig(base_dir=tmp_path)
    source = LahmanSource(cache_config=cache_config)

    # Mock remote GitHub mirror
    respx.get(f"{LAHMAN_GITHUB_BASE}/Batting.csv").mock(
        return_value=httpx.Response(200, content=SAMPLE_BATTING_CSV.encode("utf-8"))
    )

    # 1. First fetch extracts from network and compiles to processed Parquet
    batting_table = source.batting()
    assert len(batting_table) == 2
    assert batting_table["HR"].to_pylist() == [54, 58]

    # Verify two-tier directory structures exist
    raw_file = cache_config.lahman_dir / "raw" / "Batting.csv"
    processed_file = cache_config.lahman_dir / "processed" / "Batting.parquet"
    assert raw_file.exists()
    assert processed_file.exists()

    # Verify manifest
    assert source.extractor.manifest.is_completed("Batting")

    # 2. Second fetch reads directly from local Parquet cache without network calls
    respx.get(f"{LAHMAN_GITHUB_BASE}/Batting.csv").mock(return_value=httpx.Response(500))
    cached_table = source.batting(refresh=False)
    assert len(cached_table) == 2


def test_lahman_import_local_archive_zip(tmp_path: Path) -> None:
    cache_config = CacheConfig(base_dir=tmp_path)
    source = LahmanSource(cache_config=cache_config)

    # Create a simulated SABR Box zip download
    zip_path = tmp_path / "lahman-2025-csv.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("People.csv", SAMPLE_PEOPLE_CSV)
        zf.writestr("Batting.csv", SAMPLE_BATTING_CSV)

    # Import the local archive
    imported_count = source.import_archive(zip_path)
    assert imported_count == 2

    # Verify files in processed/
    people_parquet = cache_config.lahman_dir / "processed" / "People.parquet"
    batting_parquet = cache_config.lahman_dir / "processed" / "Batting.parquet"
    assert people_parquet.exists()
    assert batting_parquet.exists()

    # Query tables via source without any network calls
    people_tbl = source.people(refresh=False)
    assert len(people_tbl) == 2
    assert people_tbl["nameFirst"].to_pylist() == ["David", "Shohei"]

    bat_tbl = source.batting(refresh=False)
    assert len(bat_tbl) == 2
    assert bat_tbl["HR"].to_pylist() == [54, 58]
