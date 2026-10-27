"""Minor-league Statcast pitches: separate dataset, `minors=true`, level filters, calendars."""

import csv
import io
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.sources import catalog
from baseballpy.sources.statcast.extractor import (
    FIRST_MINORS_SEASON,
    MLB_SEASONS_URL,
    SAVANT_BASE_URL,
    StatcastExtractor,
    StatcastQuery,
)
from baseballpy.sources.statcast.schema import STATCAST_SCHEMA

FIXTURE = Path(__file__).parent / "fixtures" / "statcast" / "live_2024.csv"


def _csv_for_window(request: httpx.Request) -> httpx.Response:
    """The live 2024 fixture with a window-unique game_pk (unique pitch keys)."""
    start = request.url.params["game_date_gt"]
    end = request.url.params["game_date_lt"]
    rows = list(csv.reader(io.StringIO(FIXTURE.read_text("utf-8"))))
    header, body = rows[0], rows[1:]
    pk, day = header.index("game_pk"), header.index("game_date")
    for row in body:
        row[pk] = start.replace("-", "")
        row[day] = end
    buf = io.StringIO()
    csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n").writerows([header, *body])
    return httpx.Response(200, content=buf.getvalue().encode("utf-8"))


def _calendar(request: httpx.Request) -> httpx.Response:
    sport = int(request.url.params["sportId"])
    spans = {
        11: ("2024-03-29", "2024-09-28"),
        12: ("2024-04-05", "2024-09-15"),
        13: ("2024-04-05", "2024-09-08"),
        14: ("2024-04-05", "2024-09-08"),
    }
    year = request.url.params["season"]
    start, end = (d.replace("2024", year) for d in spans[sport])
    return httpx.Response(
        200,
        json={"seasons": [{"regularSeasonStartDate": start, "postSeasonEndDate": end}]},
    )


def test_dataset_is_registered_with_the_same_schema_and_key() -> None:
    catalog.register_all()
    minors = get_dataset("statcast", "pitches_minors")
    mlb = get_dataset("statcast", "pitches")
    assert minors.schema == mlb.schema == STATCAST_SCHEMA
    assert minors.keys == mlb.keys == ("game_pk", "at_bat_number", "pitch_number")
    assert (minors.view, minors.partition) == ("statcast_pitches_minors", "season")


def test_query_params_and_rules() -> None:
    query = StatcastQuery(minors=True)
    assert query.params() == {"minors": "true"} and query.is_unfiltered
    level = StatcastQuery(minors=True, levels=("AAA", "A"))
    assert level.params() == {"minors": "true", "hfLevel": "AAA|A|"} and not level.is_unfiltered
    assert StatcastQuery.from_filters({"minors": True, "levels": ["AAA"]}).levels == ("AAA",)
    with pytest.raises(ValueError, match="requires minors=True"):
        StatcastQuery(levels=("AAA",))


@respx.mock
def test_minor_league_population_goes_to_its_own_dataset(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 1, 1))
    extractor = StatcastExtractor(cache_config=lake, chunk_days=5)
    route = respx.get(SAVANT_BASE_URL).mock(side_effect=_csv_for_window)
    table = extractor.extract("2024-06-01", "2024-06-03", query=StatcastQuery(minors=True))
    assert table.num_rows > 0
    assert dict(route.calls[0].request.url.params)["minors"] == "true"
    assert len(list(lake.processed_dir("statcast", "pitches_minors").rglob("*.parquet"))) == 1
    assert not list(lake.processed_dir("statcast", "pitches").rglob("*.parquet"))
    assert lake.raw_dir("statcast", "pitches_minors", 2024).exists()
    assert not lake.raw_dir("statcast", "pitches", 2024).exists()


@respx.mock
def test_level_filter_is_returned_but_never_persisted(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 1, 1))
    extractor = StatcastExtractor(cache_config=lake)
    route = respx.get(SAVANT_BASE_URL).mock(side_effect=_csv_for_window)
    table = extractor.extract(
        "2024-06-01", "2024-06-03", query=StatcastQuery(minors=True, levels=("AAA",))
    )
    assert table.num_rows > 0
    assert dict(route.calls[0].request.url.params)["hfLevel"] == "AAA|"
    assert not list(lake.processed_dir("statcast", "pitches_minors").rglob("*.parquet"))


@respx.mock
def test_minor_calendar_is_the_union_of_sports_11_to_14_and_cached(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 10, 27))
    extractor = StatcastExtractor(cache_config=lake)
    route = respx.get(MLB_SEASONS_URL).mock(side_effect=_calendar)
    assert extractor.season_window(2024, minors=True) == (date(2024, 3, 29), date(2024, 9, 28))
    assert extractor.season_window(2024, minors=True) == (date(2024, 3, 29), date(2024, 9, 28))
    assert route.call_count == 4, "one request per sport, then served from the cache"
    assert sorted(int(c.request.url.params["sportId"]) for c in route.calls) == [11, 12, 13, 14]


@respx.mock
def test_seasons_before_minor_league_tracking_are_skipped_without_requests(tmp_path: Path) -> None:
    extractor = StatcastExtractor(cache_config=LakeConfig(home=tmp_path))
    savant = respx.get(SAVANT_BASE_URL).mock(side_effect=_csv_for_window)
    calendar = respx.get(MLB_SEASONS_URL).mock(side_effect=_calendar)
    report = extractor.ingest_season(2019, minors=True)
    assert report.chunks == 0 and "before 2021" in (report.skipped_reason or "")
    assert savant.call_count == 0 and calendar.call_count == 0
    assert FIRST_MINORS_SEASON == 2021


@respx.mock
def test_ingest_all_minors_starts_in_2021_and_resumes(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2022, 1, 1))
    extractor = StatcastExtractor(cache_config=lake, chunk_days=100)
    respx.get(MLB_SEASONS_URL).mock(side_effect=_calendar)
    route = respx.get(SAVANT_BASE_URL).mock(side_effect=_csv_for_window)
    reports = extractor.ingest_all(end=2021, minors=True)
    assert [r.season for r in reports] == [2021]
    assert reports[0].rows > 0 and reports[0].duplicate_keys == 0
    first_calls = route.call_count
    again = extractor.ingest_all(end=2021, minors=True)
    assert again[0].cached_chunks == again[0].chunks and route.call_count == first_calls
