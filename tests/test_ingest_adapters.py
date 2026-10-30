"""Tests for source ingest adapters and registration."""

import sys
from collections.abc import Generator, Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pyarrow as pa
import pytest

from baseballpy.ingest.adapters import ADAPTERS, IngestAdapter
from baseballpy.ingest.results import counts_to_result
from baseballpy.ingest.types import JobStatus, Selection, make_job
from baseballpy.sources.adapters import register_all_adapters
from baseballpy.sources.chadwick.adapter import ChadwickAdapter
from baseballpy.sources.chadwick.ingest import IngestOutcome
from baseballpy.sources.lahman.adapter import LahmanAdapter
from baseballpy.sources.mlb_api.adapter import MlbApiAdapter
from baseballpy.sources.retrosheet.adapter import RetrosheetAdapter
from baseballpy.sources.statcast.adapter import StatcastAdapter


@pytest.fixture(autouse=True)
def clean_adapters() -> Generator[None, None, None]:
    """Isolate tests modifying the ADAPTERS registry."""
    saved = dict(ADAPTERS)
    ADAPTERS.clear()
    yield
    ADAPTERS.clear()
    ADAPTERS.update(saved)


# ----------------------------------------------------------------------
# counts_to_result unit tests
# ----------------------------------------------------------------------


def test_counts_to_result_empty() -> None:
    job = make_job("test", "task")
    res = counts_to_result(job, [])
    assert res.status == JobStatus.COMPLETED
    assert res.rows == 0
    assert res.detail == ""


def test_counts_to_result_all_none() -> None:
    job = make_job("test", "task")
    res = counts_to_result(job, [None, None])
    assert res.status == JobStatus.SKIPPED
    assert res.rows is None
    assert res.detail == "already complete"

    res_custom = counts_to_result(job, [None], detail="custom skip")
    assert res_custom.status == JobStatus.SKIPPED
    assert res_custom.rows is None
    assert res_custom.detail == "custom skip"


def test_counts_to_result_mixed_and_numeric() -> None:
    job = make_job("test", "task")
    res = counts_to_result(job, [10, None, 25])
    assert res.status == JobStatus.COMPLETED
    assert res.rows == 35

    res_zero = counts_to_result(job, [0, None])
    assert res_zero.status == JobStatus.COMPLETED
    assert res_zero.rows == 0


# ----------------------------------------------------------------------
# Registration tests
# ----------------------------------------------------------------------


def test_register_all_adapters_idempotent() -> None:
    assert len(ADAPTERS) == 0
    register_all_adapters()
    assert set(ADAPTERS.keys()) == {
        "statcast",
        "mlb_api",
        "lahman",
        "chadwick",
        "retrosheet",
    }
    # Second call should be a no-op
    register_all_adapters()
    assert len(ADAPTERS) == 5


def test_adapters_module_import_does_not_construct_orchestrators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Unload baseballpy.sources.adapters if loaded
    sys.modules.pop("baseballpy.sources.adapters", None)

    constructed = {"count": 0}

    def count_construction(*args: Any, **kwargs: Any) -> None:
        constructed["count"] += 1

    monkeypatch.setattr(
        "baseballpy.sources.statcast.extractor.StatcastExtractor.__init__",
        count_construction,
    )
    monkeypatch.setattr(
        "baseballpy.sources.mlb_api.api.MlbApiSource.__init__",
        count_construction,
    )
    monkeypatch.setattr(
        "baseballpy.sources.lahman.api.LahmanSource.__init__",
        count_construction,
    )
    monkeypatch.setattr(
        "baseballpy.sources.retrosheet.api.RetrosheetSource.__init__",
        count_construction,
    )

    import baseballpy.sources.adapters  # noqa: F401

    assert constructed["count"] == 0


# ----------------------------------------------------------------------
# StatcastAdapter tests
# ----------------------------------------------------------------------


@dataclass
class FakeStatcastSeasonReport:
    season: int
    chunks: int
    rows: int
    cached_chunks: int
    duplicate_keys: int = 0
    skipped_reason: str | None = None


@dataclass
class FakeLeaderboardReport:
    slug: str
    seasons: dict[int, int | None]
    unsupported: str | None = None


@dataclass
class FakeGameFeedReport:
    season: int
    games: int
    fetched: int
    cached: int


class FakeStatcastExtractor:
    def __init__(self) -> None:
        self.calls: list[tuple[int, bool, bool]] = []
        self.report = FakeStatcastSeasonReport(2023, chunks=5, rows=1500, cached_chunks=0)

    def ingest_season(
        self, season: int, refresh: bool = False, minors: bool = False
    ) -> FakeStatcastSeasonReport:
        self.calls.append((season, refresh, minors))
        return self.report


class FakeStatcastLeaderboards:
    def __init__(self) -> None:
        self.calls: list[tuple[list[int] | None, bool]] = []
        self.reports = [
            FakeLeaderboardReport("exit_velocity", {2023: 120}),
            FakeLeaderboardReport("sprint_speed", {2023: None}),
        ]

    def ingest_all(
        self, years: list[int] | None = None, refresh: bool = False
    ) -> list[FakeLeaderboardReport]:
        self.calls.append((years, refresh))
        return self.reports


class FakeStatcastGameFeed:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int | None, bool]] = []
        self.report = FakeGameFeedReport(2023, games=10, fetched=2, cached=8)

    def ingest_season(
        self, season: int, max_games: int | None = None, refresh: bool = False
    ) -> FakeGameFeedReport:
        self.calls.append((season, max_games, refresh))
        return self.report


def test_statcast_adapter_protocol_and_seasons() -> None:
    adapter = StatcastAdapter()
    assert isinstance(adapter, IngestAdapter)
    seasons = adapter.all_seasons()
    assert 2008 in seasons
    assert 2024 in seasons


def test_statcast_adapter_plan() -> None:
    adapter = StatcastAdapter()

    # Empty seasons -> empty list
    assert adapter.plan(Selection(seasons=())) == []

    # Default datasets for 2023 (>= 2021 includes minors)
    jobs_2023 = adapter.plan(Selection(seasons=(2023,)))
    assert [j.task for j in jobs_2023] == ["documents", "pitches", "pitches", "leaderboards"]
    assert jobs_2023[1].param("minors") is None
    assert jobs_2023[2].param("minors") is True

    # Pre-2021 season omits pitches_minors
    jobs_2019 = adapter.plan(Selection(seasons=(2019,)))
    assert [j.task for j in jobs_2019] == ["documents", "pitches", "leaderboards"]

    # Explicit dataset filter including opt-in game_feed
    jobs_filtered = adapter.plan(Selection(seasons=(2023,), datasets=("game_feed", "pitches")))
    tasks = {j.task for j in jobs_filtered}
    assert tasks == {"game_feed", "pitches"}

    # Unknown dataset
    with pytest.raises(ValueError, match="unknown dataset"):
        adapter.plan(Selection(seasons=(2023,), datasets=("unsupported_dataset",)))


def test_statcast_adapter_run() -> None:
    ext = FakeStatcastExtractor()
    lb = FakeStatcastLeaderboards()
    gf = FakeStatcastGameFeed()
    adapter = StatcastAdapter(extractor=ext, leaderboards=lb, game_feed=gf)

    # pitches completed
    res = adapter.run(make_job("statcast", "pitches", season=2023))
    assert res.status == JobStatus.COMPLETED
    assert res.rows == 1500

    # pitches skipped with reason
    ext.report = FakeStatcastSeasonReport(2020, 0, 0, 0, skipped_reason="no minor-league data")
    res_skip_reason = adapter.run(make_job("statcast", "pitches", season=2020, minors=True))
    assert res_skip_reason.status == JobStatus.SKIPPED
    assert res_skip_reason.detail == "no minor-league data"

    # pitches cached
    ext.report = FakeStatcastSeasonReport(2023, 5, 1000, 5)
    res_cached = adapter.run(make_job("statcast", "pitches", season=2023))
    assert res_cached.status == JobStatus.SKIPPED
    assert res_cached.rows is None

    # leaderboards
    res_lb = adapter.run(make_job("statcast", "leaderboards", season=2023))
    assert res_lb.status == JobStatus.COMPLETED
    assert res_lb.rows == 120

    # game_feed completed
    res_gf = adapter.run(make_job("statcast", "game_feed", season=2023))
    assert res_gf.status == JobStatus.COMPLETED
    assert res_gf.rows == 2

    # game_feed all cached
    gf.report = FakeGameFeedReport(2023, games=10, fetched=0, cached=10)
    res_gf_cached = adapter.run(make_job("statcast", "game_feed", season=2023))
    assert res_gf_cached.status == JobStatus.SKIPPED
    assert res_gf_cached.detail == "already complete"

    # unknown task
    with pytest.raises(ValueError, match="unknown task"):
        adapter.run(make_job("statcast", "unknown"))


# ----------------------------------------------------------------------
# MlbApiAdapter tests
# ----------------------------------------------------------------------


@dataclass
class FakeEndpointReport:
    name: str
    requests: int
    rows: int
    cached: int
    unsupported: str | None = None
    missing: int = 0
    raw_only: int = 0
    errors: tuple[str, ...] = ()


class FakeMlbApiSource:
    def __init__(self) -> None:
        self.ref_reports = [FakeEndpointReport("teams", requests=2, rows=30, cached=0)]
        self.season_reports = [FakeEndpointReport("schedule", requests=5, rows=2430, cached=1)]
        self.history_reports = [FakeEndpointReport("career_stats", requests=1, rows=500, cached=0)]
        self.people_reports = [FakeEndpointReport("people_stats_season_hitting", 25, 900, 0)]
        self.people_calls: list[tuple[int, int | None]] = []
        self.season_calls: list[tuple[int, bool, int | None]] = []

    def ingest_reference(self, refresh: bool = False) -> list[FakeEndpointReport]:
        return self.ref_reports

    def ingest_season(
        self,
        season: int,
        sport_ids: tuple[int, ...] | None = None,
        include_games: bool = False,
        max_games: int | None = None,
        include_history: bool = False,
        include_awards: bool = True,
        include_people_stats: bool = False,
        max_people: int | None = None,
        refresh: bool = False,
    ) -> list[FakeEndpointReport]:
        self.season_calls.append((season, include_games, max_games))
        return self.season_reports

    def ingest_history(self, season: int, refresh: bool = False) -> list[FakeEndpointReport]:
        return self.history_reports

    def ingest_people_stats(
        self, season: int, max_people: int | None = None, refresh: bool = False
    ) -> list[FakeEndpointReport]:
        self.people_calls.append((season, max_people))
        return self.people_reports


def test_mlb_api_adapter_protocol_and_plan() -> None:
    adapter = MlbApiAdapter(FakeMlbApiSource())
    assert isinstance(adapter, IngestAdapter)
    assert 1876 in adapter.all_seasons()

    # Empty seasons -> only reference job
    assert adapter.plan(Selection(seasons=())) == [make_job("mlb_api", "reference")]

    # With season -> reference + season
    jobs = adapter.plan(Selection(seasons=(2023,)))
    assert [j.task for j in jobs] == ["reference", "season"]
    assert jobs[0].params == ()
    assert jobs[1].param("season") == 2023

    # Opt-in datasets
    jobs_opt = adapter.plan(Selection(seasons=(2023,), datasets=("games", "history")))
    assert len(jobs_opt) == 2
    assert jobs_opt[0].param("games") is True
    assert jobs_opt[1].task == "history"

    with pytest.raises(ValueError, match="unknown dataset"):
        adapter.plan(Selection(datasets=("bad_dataset",)))


def test_mlb_api_adapter_run() -> None:
    fake_source = FakeMlbApiSource()
    adapter = MlbApiAdapter(fake_source)

    # reference
    res_ref = adapter.run(make_job("mlb_api", "reference"))
    assert res_ref.status == JobStatus.COMPLETED
    assert res_ref.rows == 30

    # reference all cached (requests == cached)
    fake_source.ref_reports = [FakeEndpointReport("teams", requests=2, rows=30, cached=2)]
    res_ref_cached = adapter.run(make_job("mlb_api", "reference"))
    assert res_ref_cached.status == JobStatus.SKIPPED

    # season
    res_season = adapter.run(make_job("mlb_api", "season", season=2023))
    assert res_season.status == JobStatus.COMPLETED
    assert res_season.rows == 2430

    # history
    res_hist = adapter.run(make_job("mlb_api", "history", season=2023))
    assert res_hist.status == JobStatus.COMPLETED
    assert res_hist.rows == 500

    # unknown task
    with pytest.raises(ValueError, match="unknown task"):
        adapter.run(make_job("mlb_api", "unknown"))


# ----------------------------------------------------------------------
# LahmanAdapter tests
# ----------------------------------------------------------------------


class FakeLahmanSource:
    def __init__(self) -> None:
        self.tables = ["People", "Batting", "Pitching"]

    def list_tables(self) -> list[str]:
        return list(self.tables)

    def load_table(self, table_name: str, refresh: bool = False) -> SimpleNamespace:
        if table_name not in self.tables:
            raise KeyError(table_name)
        return SimpleNamespace(
            table=pa.table({"col": [1, 2, 3]}), from_cache=table_name == "People"
        )


def test_lahman_adapter() -> None:
    fake = FakeLahmanSource()
    adapter = LahmanAdapter(fake)
    assert isinstance(adapter, IngestAdapter)
    assert adapter.all_seasons() == []

    # plan with empty seasons -> all tables
    jobs = adapter.plan(Selection(seasons=()))
    assert len(jobs) == 3
    assert [j.param("name") for j in jobs] == ["People", "Batting", "Pitching"]

    # plan with datasets filter
    jobs_filter = adapter.plan(Selection(datasets=("People",)))
    assert len(jobs_filter) == 1
    assert jobs_filter[0].param("name") == "People"

    # plan with unknown table
    with pytest.raises(ValueError, match="unknown table"):
        adapter.plan(Selection(datasets=("NonExistent",)))

    # run table
    res = adapter.run(make_job("lahman", "table", name="People"))
    assert res.status == JobStatus.COMPLETED
    assert res.rows == 3 and res.cache_hit  # the source said this table came from a cache
    assert not adapter.run(make_job("lahman", "table", name="Batting")).cache_hit

    # names ignore letter case and are reported back as the source spells them
    assert [j.param("name") for j in adapter.plan(Selection(datasets=("people", "BATTING")))] == [
        "People",
        "Batting",
    ]

    # run unknown task
    with pytest.raises(ValueError, match="unknown task"):
        adapter.run(make_job("lahman", "other"))


# ----------------------------------------------------------------------
# ChadwickAdapter tests
# ----------------------------------------------------------------------


CHADWICK_ROWS = {
    "register": 40,
    "register_countries": 2,
    "register_links": 7,
    "register_names": 3,
}


def test_chadwick_adapter() -> None:
    calls: list[tuple[list[str] | None, bool]] = []

    def fake_loader(datasets: Sequence[str] | None, refresh: bool) -> IngestOutcome:
        calls.append((None if datasets is None else list(datasets), refresh))
        rows = {d: n for d, n in CHADWICK_ROWS.items() if datasets is None or d in datasets}
        built = {d: pa.table({"x": [1]}) for d in rows} if refresh else {}
        return IngestOutcome(rows=rows, tables=built)

    adapter = ChadwickAdapter(loader=fake_loader)
    assert isinstance(adapter, IngestAdapter)
    assert adapter.all_seasons() == []

    # every registered dataset is accepted; selecting all of them is the plain job
    assert adapter.plan(Selection(seasons=())) == [make_job("chadwick", "register")]
    assert adapter.plan(Selection(seasons=(2023,))) == [make_job("chadwick", "register")]
    every = tuple(CHADWICK_ROWS)
    assert adapter.plan(Selection(datasets=every)) == [make_job("chadwick", "register")]

    # a subset is carried in the job parameters, in registry order
    subset = adapter.plan(Selection(datasets=("register_names", "register_links")))
    assert subset == [make_job("chadwick", "register", datasets="register_links,register_names")]
    with pytest.raises(ValueError, match="unknown dataset"):
        adapter.plan(Selection(datasets=("invalid",)))

    # run: rows are summed, the detail names each dataset
    res = adapter.run(make_job("chadwick", "register"), refresh=True)
    assert res.status == JobStatus.COMPLETED
    assert res.rows == sum(CHADWICK_ROWS.values())
    assert "register_names=3" in res.detail and not res.cache_hit  # data was typed
    res = adapter.run(subset[0])
    assert res.cache_hit  # nothing was typed: everything came from the cache
    assert res.rows == 10 and calls == [(None, True), (["register_links", "register_names"], False)]

    # unknown task
    with pytest.raises(ValueError, match="unknown task"):
        adapter.run(make_job("chadwick", "unknown"))


# ----------------------------------------------------------------------
# RetrosheetAdapter tests
# ----------------------------------------------------------------------


@dataclass
class FakeRetroSeasonReport:
    year: int
    datasets: dict[str, int | None]


class FakeRetroDownloader:
    def seasons(self) -> list[int]:
        return [1920, 2023]


class FakeRetrosheetSource:
    def __init__(self) -> None:
        self.downloader = FakeRetroDownloader()
        self.ref_data: dict[str, int | None] = {"ref_parks": 150}
        self.season_data: dict[str, int | None] = {"events": 5000, "gamelogs": None}

    def ingest_reference(self, refresh: bool = False) -> dict[str, int | None]:
        return self.ref_data

    def ingest_season(
        self,
        year: int,
        datasets: tuple[str, ...] | None = None,
        refresh: bool = False,
    ) -> FakeRetroSeasonReport:
        return FakeRetroSeasonReport(year=year, datasets=self.season_data)


def test_retrosheet_adapter() -> None:
    fake = FakeRetrosheetSource()
    adapter = RetrosheetAdapter(fake)
    assert isinstance(adapter, IngestAdapter)
    assert adapter.all_seasons() == [1920, 2023]

    # plan empty seasons -> only reference job
    assert adapter.plan(Selection(seasons=())) == [make_job("retrosheet", "reference")]

    # plan with seasons -> reference + season
    jobs = adapter.plan(Selection(seasons=(2023,)))
    assert [j.task for j in jobs] == ["reference", "season"]
    assert jobs[1].param("datasets") is None

    # plan with dataset filter for season datasets
    jobs_filtered = adapter.plan(Selection(seasons=(2023,), datasets=("events", "gamelogs")))
    assert len(jobs_filtered) == 1
    assert jobs_filtered[0].param("datasets") == "events,gamelogs"

    # plan with reference dataset only
    jobs_ref_only = adapter.plan(Selection(datasets=("reference",)))
    assert len(jobs_ref_only) == 1
    assert jobs_ref_only[0].task == "reference"

    # unknown dataset
    with pytest.raises(ValueError, match="unknown dataset"):
        adapter.plan(Selection(datasets=("bad_retro",)))

    # run reference
    res_ref = adapter.run(make_job("retrosheet", "reference"))
    assert res_ref.status == JobStatus.COMPLETED
    assert res_ref.rows == 150

    # run season
    res_season = adapter.run(make_job("retrosheet", "season", season=2023))
    assert res_season.status == JobStatus.COMPLETED
    assert res_season.rows == 5000

    # unknown task
    with pytest.raises(ValueError, match="unknown task"):
        adapter.run(make_job("retrosheet", "unknown"))


def test_limit_bounds_the_opt_in_fan_out_of_mlb_and_statcast_jobs() -> None:
    mlb_source = FakeMlbApiSource()
    mlb = MlbApiAdapter(mlb_source)
    selection = Selection(seasons=(2023,), datasets=("games", "people_stats", "season"), limit=7)
    jobs = {(j.task, bool(j.param("games", False))): j for j in mlb.plan(selection)}
    assert jobs[("season", True)].limit == 7
    assert jobs[("people_stats", False)].limit == 7
    assert jobs[("season", False)].limit is None  # the default season job is never bounded

    mlb.run(jobs[("season", True)])
    mlb.run(jobs[("people_stats", False)])
    assert mlb_source.season_calls == [(2023, True, 7)]
    assert mlb_source.people_calls == [(2023, 7)]

    feed = FakeStatcastGameFeed()
    statcast = StatcastAdapter(
        extractor=FakeStatcastExtractor(), leaderboards=FakeStatcastLeaderboards(), game_feed=feed
    )
    (job,) = statcast.plan(Selection(seasons=(2023,), datasets=("game_feed",), limit=3))
    statcast.run(job)
    assert feed.calls == [(2023, 3, False)]


def test_unbounded_selection_plans_jobs_without_a_limit() -> None:
    jobs = MlbApiAdapter(FakeMlbApiSource()).plan(
        Selection(seasons=(2023,), datasets=("games", "people_stats"))
    )
    assert jobs
    assert all(job.limit is None and job.param("limit") is None for job in jobs)


def test_mlb_adapter_selects_any_registered_dataset_by_name() -> None:
    from baseballpy.sources.mlb_api.adapter import MlbApiAdapter

    adapter = MlbApiAdapter()
    jobs = adapter.plan(Selection(seasons=(2025,), datasets=("team_alumni", "ref_sports")))
    assert [(j.task, j.param("name"), j.param("season")) for j in jobs] == [
        ("endpoint", "team_alumni", 2025),
        ("endpoint", "ref_sports", None),
    ]
    assert [j.task for j in adapter.plan(Selection(seasons=(2025,), datasets=("season",)))] == [
        "season"
    ]
    with pytest.raises(ValueError, match=r"unknown dataset\(s\) for mlb_api.*'nope'"):
        adapter.plan(Selection(seasons=(2025,), datasets=("nope",)))
