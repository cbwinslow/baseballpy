"""Statcast pitch coverage: multi-era schema, typed query filters, season windows and ingestion."""

import csv
import io
import json
from datetime import date
from pathlib import Path

import httpx
import pyarrow as pa
import pytest
import respx

from baseballpy.core.config import LakeConfig, QuarantineConfig
from baseballpy.core.quarantine import Quarantine
from baseballpy.core.upstream import Fingerprint, stored_fingerprint
from baseballpy.sources.statcast.extractor import (
    MLB_SEASONS_URL,
    SAVANT_BASE_URL,
    StatcastExtractor,
    StatcastQuery,
)
from baseballpy.sources.statcast.normalizer import StatcastNormalizer
from baseballpy.sources.statcast.schema import STATCAST_SCHEMA

FIXTURES = Path(__file__).parent / "fixtures" / "statcast"
ERAS = ["2008", "2015", "2020", "2024", "2025", "2024post"]


@pytest.mark.parametrize("era", ERAS)
def test_every_era_fixture_matches_the_schema_exactly(era: str, tmp_path: Path) -> None:
    """Live headers of every era are fully covered: nothing falls into ``_extras``."""
    quarantine = Quarantine(QuarantineConfig(base_dir=tmp_path / "q"))
    raw = (FIXTURES / f"live_{era}.csv").read_bytes()
    table = StatcastNormalizer(quarantine=quarantine).normalize(raw)
    assert table.schema.names == STATCAST_SCHEMA.names
    assert table.column("_extras").null_count == table.num_rows
    assert table.num_rows >= 3
    for key in ("game_pk", "at_bat_number", "pitch_number"):
        assert table.column(key).null_count == 0
    assert not list((tmp_path / "q").rglob("*.jsonl"))


def test_schema_has_every_live_column_and_no_invented_ones() -> None:
    header = next(csv.reader(io.StringIO((FIXTURES / "live_2024.csv").read_text("utf-8"))))
    schema_cols = [n for n in STATCAST_SCHEMA.names if n != "_extras"]
    assert sorted(schema_cols) == sorted(header)
    assert len(header) == 119
    assert "pitcher_1" not in schema_cols and "fielder_2_1" not in schema_cols


def test_era_specific_columns_are_null_before_they_existed() -> None:
    old = StatcastNormalizer().normalize((FIXTURES / "live_2008.csv").read_bytes())
    new = StatcastNormalizer().normalize((FIXTURES / "live_2024.csv").read_bytes())
    assert old.column("bat_speed").null_count == old.num_rows
    assert (
        old.column("launch_speed").null_count == old.num_rows
    )  # PITCHf/x era: no batted-ball data
    assert new.column("launch_speed").null_count < new.num_rows
    assert new.schema.field("age_pit").type == pa.int16()
    assert new.schema.field("home_win_exp").type == pa.float32()
    assert new.schema.field("game_type").type == STATCAST_SCHEMA.field("game_type").type


def test_query_params_and_validation() -> None:
    assert StatcastQuery().is_unfiltered and StatcastQuery().params() == {}
    query = StatcastQuery(game_types=("R", "F"), team="NYY", player_type="batter")
    assert query.params() == {"hfGT": "R|F|", "team": "NYY", "player_type": "batter"}
    assert not query.is_unfiltered
    assert StatcastQuery(player_type="pitcher").is_unfiltered, "perspective does not change rows"
    with pytest.raises(ValueError, match="unknown game type"):
        StatcastQuery(game_types=("Z",))
    with pytest.raises(ValueError, match="player_type"):
        StatcastQuery(player_type="umpire")
    with pytest.raises(TypeError, match="unsupported Statcast filter"):
        StatcastQuery.from_filters({"hfSea": "2024|"})


def _by_window(request: httpx.Request) -> httpx.Response:
    """Savant stand-in: the live 2024 fixture with a window-unique game_pk (unique pitch keys)."""
    start = request.url.params["game_date_gt"]
    end = request.url.params["game_date_lt"]
    rows = list(csv.reader(io.StringIO((FIXTURES / "live_2024.csv").read_text("utf-8"))))
    header, body = rows[0], rows[1:]
    pk, day = header.index("game_pk"), header.index("game_date")
    for row in body:
        row[pk] = start.replace("-", "")
        row[day] = end  # the pitches belong to the last day of the window that was asked for
    buf = io.StringIO()
    csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n").writerows([header, *body])
    return httpx.Response(200, content=buf.getvalue().encode("utf-8"))


def _season_json(year: int) -> dict[str, object]:
    return {
        "seasons": [
            {
                "seasonId": str(year),
                "springStartDate": f"{year}-02-20",
                "regularSeasonStartDate": f"{year}-03-25",
                "postSeasonEndDate": f"{year}-03-01",
            }
        ]
    }


@respx.mock
def test_filtered_queries_return_rows_but_never_touch_the_lake(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2025, 6, 1))
    extractor = StatcastExtractor(cache_config=lake, chunk_days=5)
    route = respx.get(SAVANT_BASE_URL).mock(side_effect=_by_window)
    table = extractor.extract("2024-06-01", "2024-06-03", team="NYY", game_types=("R",))
    assert table.num_rows > 0
    params = dict(route.calls[0].request.url.params)
    assert params["team"] == "NYY" and params["hfGT"] == "R|"
    assert not list(lake.processed_dir("statcast", "pitches").rglob("*.parquet"))
    plain = extractor.extract("2024-06-01", "2024-06-03")
    assert plain.num_rows > 0
    assert len(list(lake.processed_dir("statcast", "pitches").rglob("*.parquet"))) == 1


@respx.mock
def test_season_window_comes_from_the_mlb_calendar_and_is_cached(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 10, 27))
    extractor = StatcastExtractor(cache_config=lake)
    route = respx.get(MLB_SEASONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "seasons": [
                    {
                        "springStartDate": "2024-02-22",
                        "regularSeasonStartDate": "2024-03-20",
                        "postSeasonEndDate": "2024-10-30",
                    }
                ]
            },
        )
    )
    assert extractor.season_window(2024) == (date(2024, 2, 22), date(2024, 10, 30))
    assert extractor.season_window(2024) == (date(2024, 2, 22), date(2024, 10, 30))
    assert route.call_count == 1, "a past season's calendar is cached on disk"
    assert dict(route.calls[0].request.url.params)["season"] == "2024"
    cached = lake.http_cache_root / "mlb-seasons" / "2024.json"
    assert json.loads(cached.read_text("utf-8"))["springStartDate"] == "2024-02-22"


@respx.mock
def test_season_window_is_clamped_to_today_for_the_current_season(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 5, 10))
    extractor = StatcastExtractor(cache_config=lake)
    respx.get(MLB_SEASONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "seasons": [{"springStartDate": "2026-02-20", "postSeasonEndDate": "2026-10-31"}]
            },
        )
    )
    assert extractor.season_window(2026) == (date(2026, 2, 20), date(2026, 5, 10))
    assert not (lake.http_cache_root / "mlb-seasons" / "2026.json").exists()


@respx.mock
def test_season_without_dates_is_an_error(tmp_path: Path) -> None:
    extractor = StatcastExtractor(cache_config=LakeConfig(home=tmp_path))
    respx.get(MLB_SEASONS_URL).mock(return_value=httpx.Response(200, json={"seasons": []}))
    with pytest.raises(ValueError, match="no season 1800"):
        extractor.season_window(1800)


@respx.mock
def test_ingest_season_is_resumable_and_checks_pitch_keys(tmp_path: Path) -> None:
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
    first = extractor.ingest_season(2024)
    assert (first.chunks, first.cached_chunks, first.duplicate_keys) == (3, 0, 0)
    assert first.rows == 15 and route.call_count == 3
    parts = list(lake.processed_dir("statcast", "pitches").rglob("*.parquet"))
    assert sorted(p.parent.name for p in parts) == ["season=2024"] * 3
    raw_chunks = lake.dataset_manifest("statcast", "pitches", "raw", 2024).chunks()
    assert raw_chunks and all(
        (stored_fingerprint(entry) or Fingerprint("none", "")).kind == "content_sha256"
        for entry in raw_chunks.values()
    )
    again = extractor.ingest_season(2024)
    assert again.cached_chunks == 3 and route.call_count == 3, "complete season: no refetch"
    assert again.rows == first.rows


@respx.mock
def test_empty_windows_are_recorded_and_not_refetched(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 1, 1))
    extractor = StatcastExtractor(cache_config=lake, chunk_days=5)
    respx.get(MLB_SEASONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "seasons": [{"springStartDate": "2024-01-31", "postSeasonEndDate": "2024-02-04"}]
            },
        )
    )
    route = respx.get(SAVANT_BASE_URL).mock(return_value=httpx.Response(200, content=b""))
    report = extractor.ingest_season(2024)
    assert report.rows == 0 and route.call_count == 1
    parts = list(lake.processed_dir("statcast", "pitches").rglob("*.parquet"))
    assert len(parts) == 1, "an empty parquet keeps the season's schema stable"
    assert extractor.ingest_season(2024).cached_chunks == 1 and route.call_count == 1


@respx.mock
def test_duplicate_pitch_keys_are_reported(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 1, 1))
    extractor = StatcastExtractor(cache_config=lake, chunk_days=1)
    respx.get(MLB_SEASONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "seasons": [{"springStartDate": "2024-06-01", "postSeasonEndDate": "2024-06-02"}]
            },
        )
    )
    same = (FIXTURES / "live_2024.csv").read_bytes()
    respx.get(SAVANT_BASE_URL).mock(return_value=httpx.Response(200, content=same))
    report = extractor.ingest_season(2024)
    assert report.duplicate_keys == 5, "two windows with identical keys -> 5 surplus rows"


@respx.mock
def test_ingest_all_walks_each_season(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 1, 1))
    extractor = StatcastExtractor(cache_config=lake, chunk_days=5)
    seen: list[str] = []

    def seasons(request: httpx.Request) -> httpx.Response:
        year = int(request.url.params["season"])
        seen.append(str(year))
        return httpx.Response(
            200,
            json=_season_json(year)
            | {
                "seasons": [
                    {"springStartDate": f"{year}-06-01", "postSeasonEndDate": f"{year}-06-03"}
                ]
            },
        )

    respx.get(MLB_SEASONS_URL).mock(side_effect=seasons)
    respx.get(SAVANT_BASE_URL).mock(side_effect=_by_window)
    reports = extractor.ingest_all(2023, 2024)
    assert [r.season for r in reports] == [2023, 2024] and seen == ["2023", "2024"]
    assert all(r.rows == 5 for r in reports)


@respx.mock
def test_pitch_chunks_written_under_another_schema_are_refetched(tmp_path: Path) -> None:
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
    assert route.call_count == 3
    manifest = lake.dataset_manifest("statcast", "pitches")
    for key, entry in list(manifest.chunks().items()):
        manifest.put_entry(key, {**entry, "schema_sha256": "0" * 64})  # an older release wrote it
    again = extractor.ingest_season(2024)
    assert again.cached_chunks == 0 and route.call_count == 6, "stale chunks are fetched again"
