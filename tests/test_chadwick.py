"""Tests for Chadwick Bureau Player Register extraction, normalization, and resolution."""

from pathlib import Path

import httpx
import pyarrow as pa
import respx

from baseballpy.core.config import LakeConfig
from baseballpy.sources.chadwick.extractor import (
    CHADWICK_COMMITS_API,
    CHADWICK_DATA_BASE_URL,
    HEX_SHARDS,
    ChadwickExtractor,
)
from baseballpy.sources.chadwick.normalizer import ChadwickNormalizer
from baseballpy.sources.chadwick.register import ChadwickRegister
from baseballpy.sources.chadwick.schema import PlayerIdType

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


def test_chadwick_register_lookups_and_crosswalk() -> None:
    normalizer = ChadwickNormalizer()
    table = normalizer.normalize(FIXTURE_PATH.read_bytes())
    register = ChadwickRegister(table)

    assert len(register) == 5

    # 1. Resolve Shohei Ohtani by MLBAM ID
    ohtani = register.resolve(mlbam=660271)
    assert ohtani is not None
    assert ohtani.full_name == "Shohei Ohtani"
    assert ohtani.key_retro == "ohtas001"
    assert ohtani.key_bbref == "ohtansh01"
    assert ohtani.birth_year == 1994

    # 2. Resolve Aaron Judge by Retrosheet ID
    judge = register.resolve(retro="judga001")
    assert judge is not None
    assert judge.full_name == "Aaron Judge"
    assert judge.key_mlbam == 592450

    # 3. Crosswalk ID helper using PlayerIdType Enum
    retro_id = register.resolve_id(660271, PlayerIdType.MLBAM, PlayerIdType.RETRO)
    assert retro_id == "ohtas001"
    mlbam_id = register.resolve_id("judga001", PlayerIdType.RETRO, PlayerIdType.MLBAM)
    assert mlbam_id == 592450

    # 4. Search with Nickname Resolution (e.g. Mike -> Michael)
    trout = register.search_name("Michael Trout")
    assert len(trout) >= 1
    assert trout[0].key_bbref == "troutmi01"

    # 5. Fuzzy Name Search
    fuzzy_judge = register.search_name("Aron Juge", fuzzy=True, min_score=0.7)
    assert len(fuzzy_judge) >= 1
    assert fuzzy_judge[0].full_name == "Aaron Judge"


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
def test_chadwick_sharded_extractor(tmp_path: Path) -> None:
    cache_config = LakeConfig(home=tmp_path)
    extractor = ChadwickExtractor(cache_config=cache_config)

    sample_csv = FIXTURE_PATH.read_bytes()

    # Mock commit check
    respx.get(CHADWICK_COMMITS_API).mock(
        return_value=httpx.Response(200, json=[{"sha": "commit_sha_12345"}])
    )

    # Mock all 16 shards
    for shard in HEX_SHARDS:
        respx.get(f"{CHADWICK_DATA_BASE_URL}/{shard}").mock(
            return_value=httpx.Response(200, content=sample_csv)
        )
    respx.get(f"{CHADWICK_DATA_BASE_URL}/names.csv").mock(
        return_value=httpx.Response(
            200,
            content=b"key_person,name_last,name_first,name_given,name_suffix,name_matrilineal,name_nick,name_type\nohtas01,Ohtani,Shohei,Shohei,,,,alias\n",
        )
    )
    respx.get(f"{CHADWICK_DATA_BASE_URL}/links.csv").mock(
        return_value=httpx.Response(
            200,
            content=b"key_person,link_type,link_url\nohtas01,wikipedia,https://en.wikipedia.org/wiki/Shohei_Ohtani\n",
        )
    )

    # 1. First run fetches all shards and records commit SHA
    shards_data = extractor.extract(refresh=True)
    assert len(shards_data) >= 17  # 16 shards + names.csv
    assert extractor.are_shards_cached()
    assert extractor.manifest.is_completed("commit_sha")

    # 2. Normalize concatenated shards
    normalizer = ChadwickNormalizer()
    unified_table = normalizer.normalize(shards_data)
    assert len(unified_table) == 5 * 16  # 5 rows per shard * 16

    # 3. Second run reads from disk without network calls
    respx.get(CHADWICK_COMMITS_API).mock(return_value=httpx.Response(500))
    for shard in HEX_SHARDS:
        respx.get(f"{CHADWICK_DATA_BASE_URL}/{shard}").mock(return_value=httpx.Response(500))

    cached_shards = extractor.extract(refresh=False)
    assert len(cached_shards) >= 17
