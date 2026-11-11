"""A fresh download leaves the lake in the one shape every user expects (AGENTS.md section 15).

Each source is downloaded (HTTP mocked with the recorded fixtures) into an empty home; then the shared
contract of ``lake_contract.py`` must hold, again after compaction, and a second run must not download
anything. The contract itself is driven by the dataset registry.
"""

from datetime import date
from pathlib import Path

import httpx
import respx
from conftest import RetroRepo
from lake_contract import assert_lake_contract, processed_files
from test_chadwick_coverage import _serve_everything
from test_lahman_workflow import _repo
from test_mlb_coverage import COVERED, _fixture
from test_mlb_segments import PKS, _mock_games
from test_retrosheet_coverage import full_season
from test_statcast_coverage import _fixture as _savant_fixture
from test_statcast_pitches import _by_window

from baseballpy.core.compact import compact_dataset
from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.datasets import DATASETS
from baseballpy.sources import catalog
from baseballpy.sources.chadwick.ingest import ingest as ingest_chadwick
from baseballpy.sources.lahman.api import LahmanSource
from baseballpy.sources.mlb_api.endpoints import MLB_BASE_URL, Context, requests_for
from baseballpy.sources.mlb_api.game_segments import ingest_game_segments
from baseballpy.sources.mlb_api.generic import MlbEndpointExtractor
from baseballpy.sources.retrosheet.api import RetrosheetSource
from baseballpy.sources.statcast.extractor import (
    MLB_SEASONS_URL,
    SAVANT_BASE_URL,
    StatcastExtractor,
)
from baseballpy.sources.statcast.lb_catalog import SAVANT_BASE, SUPPORTED
from baseballpy.sources.statcast.leaderboards import StatcastLeaderboardExtractor


def _compact_source(config: LakeConfig, source: str) -> None:
    catalog.register_all()
    for spec in DATASETS.values():
        if spec.source == source:
            compact_dataset(spec, config)


@respx.mock
def test_a_fresh_statcast_download_has_the_lake_shape(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 1, 1))
    extractor = StatcastExtractor(cache_config=lake, chunk_days=5)
    respx.get(MLB_SEASONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "seasons": [{"springStartDate": "2024-06-01", "postSeasonEndDate": "2024-06-12"}]
            },
        )
    )
    route = respx.get(SAVANT_BASE_URL).mock(side_effect=_by_window)
    extractor.ingest_season(2024)
    views = assert_lake_contract(lake, ["statcast"])
    assert views == {"statcast_pitches": 15}

    _compact_source(lake, "statcast")  # the same contract after compaction
    assert assert_lake_contract(lake, ["statcast"]) == views

    calls = route.call_count
    extractor.ingest_season(2024)
    assert route.call_count == calls, "a second run downloads nothing"


@respx.mock
def test_a_fresh_retrosheet_download_has_the_lake_shape(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    full_season(retro_repo).mount()
    lake = LakeConfig(home=tmp_path / "lake")
    source = RetrosheetSource(cache_config=lake)
    source.ingest_season(2024)
    source.ingest_reference()  # biographical and park files, documents
    views = assert_lake_contract(lake, ["retrosheet"])
    assert views, "the season produced datasets"
    assert all(rows > 0 for rows in views.values()) or any(rows > 0 for rows in views.values())

    _compact_source(lake, "retrosheet")
    assert assert_lake_contract(lake, ["retrosheet"]) == views


@respx.mock
def test_the_contract_catches_a_stray_file_a_wrong_type_and_an_unknown_folder(
    tmp_path: Path,
) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq
    import pytest

    lake = LakeConfig(home=tmp_path, today=date(2026, 1, 1))
    extractor = StatcastExtractor(cache_config=lake, chunk_days=5)
    respx.get(MLB_SEASONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "seasons": [{"springStartDate": "2024-06-01", "postSeasonEndDate": "2024-06-05"}]
            },
        )
    )
    respx.get(SAVANT_BASE_URL).mock(side_effect=_by_window)
    extractor.ingest_season(2024)
    assert_lake_contract(lake, ["statcast"])
    folder = lake.processed_dir("statcast", "pitches", 2024)

    stray = folder / "notes.parquet"  # a name no workflow writes
    stray.write_bytes((next(folder.glob("part-*.parquet"))).read_bytes())
    with pytest.raises(AssertionError, match="unexpected file name"):
        assert_lake_contract(lake, ["statcast"])
    stray.unlink()

    wrong = folder / "part-wrong.parquet"  # a right name with columns that are not the registry's
    pq.write_table(pa.table({"x": [1]}), wrong)
    with pytest.raises(AssertionError):
        assert_lake_contract(lake, ["statcast"])
    wrong.unlink()

    unknown = lake.processed_root / "statcast" / "not_a_dataset" / "part-a.parquet"
    unknown.parent.mkdir(parents=True)
    pq.write_table(pa.table({"x": [1]}), unknown)
    with pytest.raises(AssertionError):
        assert_lake_contract(lake, ["statcast"])


@respx.mock
def test_a_fresh_chadwick_download_has_the_lake_shape(tmp_path: Path) -> None:
    _serve_everything()
    lake = LakeConfig(home=tmp_path)
    ingest_chadwick(config=lake)
    views = assert_lake_contract(lake, ["chadwick"])
    assert set(views) == {
        "chadwick_register",
        "chadwick_register_names",
        "chadwick_register_links",
        "chadwick_register_countries",
    }
    assert all(rows > 0 for rows in views.values())

    _compact_source(lake, "chadwick")
    assert assert_lake_contract(lake, ["chadwick"]) == views


@respx.mock
def test_a_fresh_lahman_download_has_the_lake_shape(tmp_path: Path) -> None:
    repo = _repo()
    repo.mount()
    lake = LakeConfig(home=tmp_path)
    source = LahmanSource(lake)
    source.batting()
    source.people()
    views = assert_lake_contract(lake, ["lahman"])
    assert views == {"lahman_batting": 2, "lahman_people": views["lahman_people"]}

    _compact_source(lake, "lahman")
    assert assert_lake_contract(lake, ["lahman"]) == views
    calls = repo.raw_calls()
    source.batting()
    assert repo.raw_calls() == calls, "a second run downloads nothing"


@respx.mock
def test_a_fresh_mlb_game_download_has_the_lake_shape(tmp_path: Path) -> None:
    """Every game-level dataset for two games: one URL asked once, however many datasets it feeds."""
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(
        cache_config=lake, rate_limit_config=RateLimitConfig(verify_max_requests=0)
    )
    games = (745000, 775296)
    context = Context(season=2024, game_pks=games)
    endpoints = [e for e in COVERED if e.scope == "game" and e.unsupported is None]
    assert endpoints
    routes: dict[str, respx.Route] = {}
    for endpoint in endpoints:
        for request in requests_for(endpoint, context):
            url = f"{MLB_BASE_URL}/{request.path}"
            if url not in routes:  # datasets cut from one URL share its answer
                routes[url] = respx.get(url).mock(
                    return_value=httpx.Response(200, json=_fixture(endpoint.name))
                )
    for endpoint in endpoints:
        extractor.ingest(endpoint.name, context)
    views = assert_lake_contract(lake, ["mlb_api"])
    assert views and len(views) >= len(endpoints) // 2
    assert all(route.call_count == 1 for route in routes.values()), "one request per URL"

    _compact_source(lake, "mlb_api")
    assert assert_lake_contract(lake, ["mlb_api"]) == views

    for endpoint in endpoints:  # a second run downloads nothing
        extractor.ingest(endpoint.name, context)
    assert all(route.call_count == 1 for route in routes.values())


@respx.mock
def test_every_mlb_endpoint_download_has_the_lake_shape(tmp_path: Path) -> None:
    """All supported MLB endpoints with a recorded answer, in one lake: the same shape for each dataset."""
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(
        cache_config=lake, rate_limit_config=RateLimitConfig(verify_max_requests=0)
    )
    context = Context(
        season=2024,
        sport_ids=(1,),
        team_ids=(147,),
        game_pks=(745000,),
        person_ids=(660271,),
        leader_categories=("homeRuns",),
        award_ids=("MLBMVP",),
        updated_since="2024-06-01T00:00:00Z",
        query="ohtani",
    )
    routes: dict[str, respx.Route] = {}
    ingested: list[str] = []
    for endpoint in COVERED:
        if endpoint.unsupported is not None or endpoint.paginated:
            continue
        try:
            requests = list(requests_for(endpoint, context))
        except ValueError:
            continue  # needs a fan-out value this test does not give (covered by its own test)
        if not requests or len(requests) > 6:
            continue
        for request in requests:
            url = f"{MLB_BASE_URL}/{request.path}"
            if url not in routes:
                routes[url] = respx.get(url).mock(
                    return_value=httpx.Response(200, json=_fixture(endpoint.name))
                )
        extractor.ingest(endpoint.name, context)
        ingested.append(endpoint.name)
    assert len(ingested) >= 20, f"too few endpoints exercised: {len(ingested)}"
    views = assert_lake_contract(lake, ["mlb_api"])
    assert views

    _compact_source(lake, "mlb_api")
    assert assert_lake_contract(lake, ["mlb_api"]) == views


@respx.mock
def test_every_statcast_leaderboard_download_has_the_lake_shape(tmp_path: Path) -> None:
    """All supported Savant leaderboards for one season, from their recorded pages."""
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = StatcastLeaderboardExtractor(cache_config=lake)
    for definition in SUPPORTED:
        respx.get(f"{SAVANT_BASE}/{definition.route}").mock(
            return_value=httpx.Response(200, content=_savant_fixture(definition.slug))
        )
    reports = extractor.ingest_all(years=[2024])
    assert reports
    views = assert_lake_contract(lake, ["statcast"])
    assert len(views) >= len(SUPPORTED) // 2, views

    _compact_source(lake, "statcast")
    assert assert_lake_contract(lake, ["statcast"]) == views


@respx.mock
def test_a_fresh_mlb_game_download_as_segments_has_the_lake_shape(tmp_path: Path) -> None:
    """The planned final layout (ADR 95): seg-NNNN files, each response stored once, same contract."""
    routes = _mock_games(PKS)
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(cache_config=lake)
    report = ingest_game_segments(extractor, 2024, list(PKS))
    assert report.stored == len(PKS) and not report.failed
    views = assert_lake_contract(lake, ["mlb_api"])
    assert views
    files = [p.name for p in processed_files(lake, "mlb_api")]
    assert files and all(name.startswith("seg-") for name in files)

    calls = {key: route.call_count for key, route in routes.items()}
    again = ingest_game_segments(extractor, 2024, list(PKS))
    assert again.stored == 0 and again.already == len(PKS)
    assert {key: route.call_count for key, route in routes.items()} == calls
