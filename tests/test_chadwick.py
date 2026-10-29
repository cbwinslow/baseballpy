"""Tests for Chadwick Bureau Player Register extraction, normalization, and resolution."""

from pathlib import Path

import httpx
import pyarrow as pa
import pytest
import respx

from baseballpy.core.config import LakeConfig
from baseballpy.sources.chadwick.extractor import (
    CHADWICK_DATA_BASE_URL,
    HEX_SHARDS,
    ChadwickExtractor,
)
from baseballpy.sources.chadwick.normalizer import ChadwickNormalizer
from baseballpy.sources.chadwick.register import ChadwickRegister
from baseballpy.sources.chadwick.schema import PlayerIdType

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "chadwick" / "people_sample.csv"


def mock_register_tree(ref: str, extra: tuple[str, ...] = ("names.csv", "links.csv")) -> None:
    """Mock ``GET /git/trees/<ref>`` for chadwickbureau/register with all 16 shards + ``extra``."""
    files = [f"data/{name}" for name in (*HEX_SHARDS, *extra)]
    respx.get(
        f"https://api.github.com/repos/chadwickbureau/register/git/trees/{ref}?recursive=1"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "truncated": False,
                "tree": [{"path": p, "type": "blob", "size": 1, "sha": "x"} for p in files],
            },
        )
    )


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

    from baseballpy.core.sources_lock import get_source_ref

    mock_register_tree(get_source_ref("chadwick_register").ref)

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
    for shard in HEX_SHARDS:
        respx.get(f"{CHADWICK_DATA_BASE_URL}/{shard}").mock(return_value=httpx.Response(500))

    cached_shards = extractor.extract(refresh=False)
    assert len(cached_shards) >= 17


_FULL_IDS_CSV = (
    "key_person,key_uuid,key_mlbam,key_retro,key_bbref,key_bbref_minors,key_fangraphs,key_npb,"
    "key_wikidata,name_last,name_first,name_given,birth_year,birth_month,birth_day,"
    "mlb_played_first,mlb_played_last\n"
    "270bfa31,270bfa31-f65b-4d2b-a54a-09dca1b6a000,660271,ohtas001,ohtansh01,otani-000sho,19755,"
    "1305137,Q4391858,Ohtani,Shohei,Shohei,1994,7,5,2018,2024\n"
    "a1b2c3d4,a1b2c3d4-0000-4000-8000-000000000001,592450,judga001,judgeaa01,judge-000aar,15640,"
    ",Q1234,Judge,Aaron,Aaron James,1992,4,26,2016,2024\n"
)


def _full_register() -> ChadwickRegister:
    table = ChadwickNormalizer().normalize(_FULL_IDS_CSV.encode())
    return ChadwickRegister(table)


def test_resolve_id_bbref_minors_is_not_confused_with_bbref() -> None:
    register = _full_register()
    assert register.resolve_id(660271, PlayerIdType.MLBAM, PlayerIdType.BBREF) == "ohtansh01"
    assert (
        register.resolve_id(660271, PlayerIdType.MLBAM, PlayerIdType.BBREF_MINORS) == "otani-000sho"
    )
    assert register.resolve_id("otani-000sho", PlayerIdType.BBREF_MINORS, PlayerIdType.MLBAM) == (
        660271
    )


def test_resolve_id_round_trips_every_id_type_in_both_directions() -> None:
    register = _full_register()
    ohtani = register.resolve(mlbam=660271)
    assert ohtani is not None
    columns = {id_type: getattr(ohtani, id_type.value) for id_type in PlayerIdType}
    assert all(value is not None for value in columns.values())
    for source in PlayerIdType:
        for target in PlayerIdType:
            assert register.resolve_id(columns[source], source, target) == columns[target], (
                source,
                target,
            )


def test_resolve_id_accepts_names_ignores_case_and_returns_none_for_unknown_ids() -> None:
    register = _full_register()
    assert register.resolve_id("OHTAS001", "key_retro", "key_mlbam") == 660271
    assert register.resolve_id("Q4391858", "wikidata", "retro") == "ohtas001"
    assert register.resolve_id(1, PlayerIdType.MLBAM, PlayerIdType.RETRO) is None
    assert register.resolve_id(592450, PlayerIdType.MLBAM, PlayerIdType.NPB) is None


def test_resolve_id_rejects_unknown_id_types() -> None:
    register = _full_register()
    with pytest.raises(ValueError, match="unknown player id type"):
        register.resolve_id(1, "key_nope", PlayerIdType.RETRO)
    with pytest.raises(ValueError, match="unknown player id type"):
        register.resolve_id(1, PlayerIdType.MLBAM, "nope")
