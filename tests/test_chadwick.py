"""Tests for Chadwick Bureau Player Register extraction, normalization, and resolution."""

from pathlib import Path

import httpx
import pyarrow as pa
import pytest
import respx

from baseballpy.core.config import CacheConfig
from baseballpy.sources.chadwick.extractor import CHADWICK_PEOPLE_URL, ChadwickExtractor
from baseballpy.sources.chadwick.normalizer import ChadwickNormalizer
from baseballpy.sources.chadwick.register import ChadwickRegister

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "chadwick" / "people_sample.csv"


def test_chadwick_normalizer_schema() -> None:
    normalizer = ChadwickNormalizer()
    csv_bytes = FIXTURE_PATH.read_bytes()
    table = normalizer.normalize(csv_bytes)

    assert len(table) == 5
    assert "key_mlbam" in table.column_names
    assert "key_retro" in table.column_names
    assert "name_last" in table.column_names
    assert pa.types.is_integer(table.schema.field("key_mlbam").type)
    assert pa.types.is_integer(table.schema.field("birth_year").type)


def test_chadwick_register_lookups() -> None:
    normalizer = ChadwickNormalizer()
    table = normalizer.normalize(FIXTURE_PATH.read_bytes())
    register = ChadwickRegister(table)

    assert len(register) == 5

    # Resolve Shohei Ohtani by MLBAM ID
    ohtani = register.resolve(mlbam=660271)
    assert ohtani is not None
    assert ohtani.full_name == "Shohei Ohtani"
    assert ohtani.key_retro == "ohtas001"
    assert ohtani.key_bbref == "ohtansh01"
    assert ohtani.birth_year == 1994

    # Resolve Aaron Judge by Retrosheet ID
    judge = register.resolve(retro="judga001")
    assert judge is not None
    assert judge.full_name == "Aaron Judge"
    assert judge.key_mlbam == 592450

    # Resolve Mike Trout by BBRef slug
    trout = register.resolve(bbref="troutmi01")
    assert trout is not None
    assert trout.full_name == "Mike Trout"

    # Resolve Mookie Betts by FanGraphs ID
    betts = register.resolve(fangraphs=13611)
    assert betts is not None
    assert betts.full_name == "Mookie Betts"

    # Search by name
    results = register.search_name("Babe Ruth")
    assert len(results) == 1
    assert results[0].key_retro == "ruthb001"


def test_chadwick_register_dataframe_interop() -> None:
    normalizer = ChadwickNormalizer()
    table = normalizer.normalize(FIXTURE_PATH.read_bytes())
    register = ChadwickRegister(table)

    polars_df = register.to_polars()
    assert len(polars_df) == 5
    assert "key_mlbam" in polars_df.columns

    nw_df = register.to_dataframe()
    assert nw_df.shape[0] == 5


@respx.mock
def test_chadwick_extractor_mocked_network(tmp_path: Path) -> None:
    cache_config = CacheConfig(base_dir=tmp_path)
    extractor = ChadwickExtractor(cache_config=cache_config)

    sample_csv = FIXTURE_PATH.read_bytes()
    respx.get(CHADWICK_PEOPLE_URL).mock(
        return_value=httpx.Response(200, content=sample_csv, headers={"ETag": '"hash123"'})
    )

    # First fetch from mocked network
    data1 = extractor.extract()
    assert data1 == sample_csv
    assert extractor.cache_file.exists()
    assert extractor.etag_file.read_text() == '"hash123"'

    # Second fetch should hit local cache without network call
    respx.get(CHADWICK_PEOPLE_URL).mock(return_value=httpx.Response(500))
    data2 = extractor.extract(refresh=False)
    assert data2 == sample_csv


@respx.mock
@pytest.mark.asyncio
async def test_chadwick_extractor_async(tmp_path: Path) -> None:
    cache_config = CacheConfig(base_dir=tmp_path)
    extractor = ChadwickExtractor(cache_config=cache_config)

    sample_csv = FIXTURE_PATH.read_bytes()
    respx.get(CHADWICK_PEOPLE_URL).mock(
        return_value=httpx.Response(200, content=sample_csv, headers={"ETag": '"etag_abc"'})
    )

    data = await extractor.extract_async()
    assert data == sample_csv
    assert extractor.cache_file.exists()
