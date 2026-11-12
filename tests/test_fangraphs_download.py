"""FanGraphs downloader: shaping, honesty, stopping at a refusal, chunks shared with the inbox."""

import json
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.core.config import FANGRAPHS_HOST, LakeConfig, RateLimitConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.http import HttpClient, HttpResult, HttpStatusError
from baseballpy.core.stores import ProcessedStore
from baseballpy.ingest.types import Job, JobStatus, Selection
from baseballpy.sources import catalog
from baseballpy.sources.fangraphs.adapter import FangraphsAdapter
from baseballpy.sources.fangraphs.download import (
    DownloadOutcome,
    download_projection,
    download_season,
)
from baseballpy.sources.fangraphs.extractor import FangraphsBlockedError, FangraphsWeb
from baseballpy.sources.fangraphs.files import BY_DATASET
from baseballpy.sources.fangraphs.ingest import chunks_of
from baseballpy.sources.fangraphs.normalizer import FangraphsNormalizer
from baseballpy.sources.fangraphs.records import column_name, projection_hash, shape_row
from baseballpy.sources.fangraphs.tables import FANGRAPHS_COLUMNS
from baseballpy.sources.fangraphs.web import FIRST_SEASON, user_agent

NAME = '<a href="statss.aspx?playerid=15640&position=OF">Aaron Judge</a>'
BAT_ROW = {
    "playerid": "15640", "Season": 2024, "Name": NAME, "Team": "NYY", "PA": 704.0, "AB": 559.0,
    "1B": 90, "BB%": 0.1832, "WAR": 10.9, "xMLBAMID": 592450.0, "-WPA": -3.4, "+WPA": 9.1,
    "AFutureColumn": 7,
}  # fmt: skip
PROJ_ROW = {"playerid": "15640", "PlayerName": "Aaron Judge", "PA": 600.0, "WAR": 8.0}


class FakeHttp:
    """A stand-in for the shared client: answers the leaderboard and projection routes."""

    def __init__(self, status: int = 200, body: bytes | None = None) -> None:
        self.status, self.forced_body = status, body
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.hooks: dict[str, Callable[[str, str], Mapping[str, str]]] = {}
        self.leaders: list[dict[str, Any]] = [BAT_ROW]
        self.projections: list[dict[str, Any]] = [PROJ_ROW]

    def set_header_hook(self, host: str, hook: Callable[[str, str], Mapping[str, str]]) -> None:
        self.hooks[host] = hook

    def get_sync(self, url: str, *, params: dict[str, str] | None = None, **_: Any) -> HttpResult:
        self.calls.append((url, dict(params or {})))
        if self.status != 200:
            raise HttpStatusError(url, self.status)
        if self.forced_body is not None:
            body = self.forced_body
        elif "/api/leaders/" in url:
            body = json.dumps({"data": self.leaders, "totalCount": len(self.leaders)}).encode()
        else:
            body = json.dumps(self.projections).encode()
        return HttpResult(url, 200, body, None, False, 0.0)


def web(tmp_path: Path, fake: FakeHttp) -> tuple[LakeConfig, FangraphsWeb]:
    config = LakeConfig(home=tmp_path)
    return config, FangraphsWeb(config, fake)  # type: ignore[arg-type]


def test_keys_become_the_column_names_the_tables_use() -> None:
    assert column_name("1B") == "n1b" and column_name("BB%") == "bb_"
    assert column_name("xMLBAMID") == "xmlbamid" and column_name("Season") == "season"
    assert column_name("-WPA") == "wpa_neg" and column_name("+WPA") == "wpa_pos"
    assert column_name("K-BB%") == "k_minus_bb_pct" and column_name("K/BB+") == "k_per_bb_plus"
    with pytest.raises(ValueError, match="collide"):
        shape_row({"BB%": 1, "bb_": 2}, {})


def test_every_existing_column_name_is_stable_under_the_rule() -> None:
    """A name that is already a column maps to itself, so a download and a file meet in one column."""
    for dataset, columns in FANGRAPHS_COLUMNS.items():
        for name, _kind in columns:
            assert column_name(name) == name, (dataset, name)


def test_the_user_agent_is_honest_and_set_for_this_host_only(tmp_path: Path) -> None:
    fake = FakeHttp()
    web(tmp_path, fake)
    agent = fake.hooks[FANGRAPHS_HOST]("GET", "https://x")["User-Agent"]
    assert agent.startswith("baseballpy/") and "github.com/cbwinslow/baseballpy" in agent
    assert agent == user_agent(agent.split("/")[1].split(" ")[0])
    for disguise in ("okhttp", "Mozilla", "Chrome", "Android", "python-requests"):
        assert disguise not in agent


@pytest.mark.parametrize("status", [403, 429, 503])
def test_a_refusal_stops_the_run_with_a_clear_message(tmp_path: Path, status: int) -> None:
    config, client = web(tmp_path, FakeHttp(status=status))
    with pytest.raises(FangraphsBlockedError, match=f"HTTP {status}.*does not retry"):
        download_season(
            "batting", 2024, config=config, web=client, normalizer=FangraphsNormalizer()
        )
    assert not list(tmp_path.rglob("*.parquet")), "nothing is stored from a refusal"


def test_a_web_page_instead_of_data_is_a_bot_challenge_and_stops_the_run(tmp_path: Path) -> None:
    config, client = web(tmp_path, FakeHttp(body=b"<html><title>Just a moment...</title>"))
    with pytest.raises(FangraphsBlockedError, match="bot challenge"):
        download_projection(
            "steamer", "bat", config=config, web=client, normalizer=FangraphsNormalizer()
        )


@respx.mock
def test_the_shared_client_makes_exactly_one_request_when_fangraphs_refuses() -> None:
    route = respx.get(f"https://{FANGRAPHS_HOST}/api/projections").mock(
        return_value=httpx.Response(403, headers={"Retry-After": "1"})
    )
    client = HttpClient(RateLimitConfig(host_rates={FANGRAPHS_HOST: 100.0}))
    with pytest.raises(HttpStatusError):
        client.get_sync(f"https://{FANGRAPHS_HOST}/api/projections", params={"type": "steamer"})
    assert route.call_count == 1


def test_the_host_is_slow_and_one_request_at_a_time() -> None:
    config = RateLimitConfig()
    assert config.host_rates[FANGRAPHS_HOST] == 0.5 and config.host_concurrency[FANGRAPHS_HOST] == 1
    assert config.host_max_attempts[FANGRAPHS_HOST] == 1


def test_a_season_is_typed_into_the_same_columns_and_unknown_keys_are_kept(tmp_path: Path) -> None:
    fake = FakeHttp()
    config, client = web(tmp_path, fake)
    out = download_season(
        "batting", 2024, config=config, web=client, normalizer=FangraphsNormalizer()
    )
    assert out.rows == {"batting": 1}
    url, params = fake.calls[0]
    assert url.endswith("/api/leaders/major-league/data")
    assert (params["stats"], params["season"], params["season1"], params["qual"], params["ind"]) == (
        "bat", "2024", "2024", "0", "1",
    )  # fmt: skip
    row = ProcessedStore(config).read(get_dataset("fangraphs", "batting")).to_pylist()[0]
    assert (row["playerid"], row["season"], row["pa"], row["xmlbamid"], row["n1b"]) == (
        15640, 2024, 704, 592450, 90,
    )  # fmt: skip
    assert row["_season"] == 2024 and row["_loaded_at"].year >= 2026 and row["wpa_neg"] is not None
    assert row["_extras"] == '{"afuturecolumn": "7"}'
    assert not (tmp_path / "quarantine").exists()
    assert (tmp_path / "raw" / "fangraphs" / "batting" / "leaders-2024.jsonl.gz").exists()


def test_a_past_season_is_not_fetched_again_but_the_current_one_always_is(tmp_path: Path) -> None:
    fake = FakeHttp()
    config, client = web(tmp_path, fake)
    kw: dict[str, Any] = {"config": config, "web": client, "normalizer": FangraphsNormalizer()}
    today = date(2026, 11, 6)
    download_season("batting", 2024, today=today, **kw)
    again = download_season("batting", 2024, today=today, **kw)
    assert again.cached and len(fake.calls) == 1
    download_season("batting", 2024, today=today, force=True, **kw)
    assert len(fake.calls) == 2
    download_season("batting", 2026, today=today, **kw)
    download_season("batting", 2026, today=today, **kw)
    assert len(fake.calls) == 4, "the current season changes, so it is fetched each time"
    with pytest.raises(ValueError, match="no leaderboard download"):
        download_season("guts", 2024, **kw)


def test_a_downloaded_season_replaces_the_same_season_from_a_file_without_duplicates(
    tmp_path: Path,
) -> None:
    fake = FakeHttp()
    config, client = web(tmp_path, fake)
    spec = get_dataset("fangraphs", "batting")
    store = ProcessedStore(config)
    normalizer = FangraphsNormalizer()
    old = normalizer.normalize_records(
        "batting", [shape_row({**BAT_ROW, "WAR": 1.0}, {"_season": "2024"})]
    )
    pieces = dict(chunks_of(BY_DATASET["batting"], old))
    assert list(pieces) == ["season-2024"], "a file is cut into the chunks a download writes"
    store.put(spec, pieces["season-2024"], chunk_id="season-2024")
    download_season("batting", 2024, config=config, web=client, normalizer=normalizer, force=True)
    rows = store.read(spec).to_pylist()
    assert len(rows) == 1 and float(rows[0]["war"]) == 10.9


def test_projection_rows_are_stored_only_when_their_values_changed(tmp_path: Path) -> None:
    fake = FakeHttp()
    config, client = web(tmp_path, fake)
    kw: dict[str, Any] = {"config": config, "web": client, "normalizer": FangraphsNormalizer()}
    first = download_projection("steamer", "bat", today=date(2026, 11, 6), **kw)
    assert first.rows == {"projection": 1}
    again = download_projection("steamer", "bat", today=date(2026, 11, 7), **kw)
    assert again.rows == {"projection": 0}, "unchanged values add nothing"
    fake.projections = [{**PROJ_ROW, "WAR": 8.5}, {"PlayerName": "No Id", "PA": 1.0}]
    moved = download_projection("steamer", "bat", today=date(2026, 11, 8), **kw)
    assert moved.rows == {"projection": 1}, "a changed player is stored, a row without an id is not"
    other = download_projection("steamerr", "bat", today=date(2026, 11, 8), **kw)
    assert other.rows == {"projection": 1}, "another system keeps its own history"
    rows = ProcessedStore(config).read(get_dataset("fangraphs", "projection")).to_pylist()
    assert len(rows) == 3
    ros = next(r for r in rows if r["_projection_system"] == "steamerr")
    assert ros["_horizon"] == "ros" and str(ros["_captured_date"]) == "2026-11-08"
    pre = [r for r in rows if r["_projection_system"] == "steamer"]
    assert {r["_horizon"] for r in pre} == {"preseason"} and len({r["_row_hash"] for r in pre}) == 2


def test_the_row_hash_follows_the_values_not_the_bookkeeping() -> None:
    a = projection_hash({"playerid": "1", "WAR": 2.0, "_captured_date": "2026-01-01"})
    assert a == projection_hash({"WAR": 2.0, "playerid": "1", "_captured_date": "2027-01-01"})
    assert a != projection_hash({"playerid": "1", "WAR": 2.5})
    assert len(a) == 32


def test_the_adapter_plans_files_by_default_and_downloads_only_when_asked() -> None:
    catalog.register_all()
    ran: list[Job] = []

    def downloader(job: Job, refresh: bool) -> DownloadOutcome:
        ran.append(job)
        return DownloadOutcome(rows={"batting": 3}, detail="x")

    adapter = FangraphsAdapter(downloader=downloader)
    assert [j.task for j in adapter.plan(Selection())] == ["inbox"]
    seasons = (2024, 2023)
    jobs = adapter.plan(
        Selection(seasons=seasons, datasets=("batting",), options=(("download", "yes"),))
    )
    assert [(j.task, j.param("season")) for j in jobs] == [("season", 2024), ("season", 2023)]
    projections = adapter.plan(Selection(datasets=("projection",), options=(("download", "true"),)))
    assert len(projections) == 32 and {j.task for j in projections} == {"projection"}
    default = adapter.plan(Selection(options=(("download", "yes"),)))
    assert len(default) == 3 + 32, "three leaderboards for this season and 32 projection runs"
    result = adapter.run(jobs[0], refresh=True)
    assert result.status is JobStatus.COMPLETED and result.rows == 3 and ran == [jobs[0]]
    with pytest.raises(ValueError, match="no downloader for fangraphs"):
        adapter.plan(Selection(datasets=("guts",), options=(("download", "yes"),)))
    assert adapter.all_seasons()[0] == FIRST_SEASON


def test_the_option_switch_reaches_the_planner_and_a_bad_one_is_refused() -> None:
    runner = CliRunner()
    ok = runner.invoke(
        main,
        [
            "ingest",
            "fangraphs",
            "-d",
            "batting",
            "--seasons",
            "2024",
            "-o",
            "download=yes",
            "--dry-run",
        ],
    )
    assert ok.exit_code == 0, ok.output
    assert "season" in ok.output and "batting" in ok.output and "inbox" not in ok.output
    bad = runner.invoke(main, ["ingest", "fangraphs", "-o", "download", "--dry-run"])
    assert bad.exit_code != 0 and "KEY=VALUE" in bad.output
    assert Selection(options=(("a", "On"),)).flag("a") and not Selection().flag("a")


def test_a_fresh_fangraphs_download_has_the_lake_shape(tmp_path: Path) -> None:
    """The shared lake contract (layout, raw integrity, typed views) holds after a download."""
    from lake_contract import assert_lake_contract

    config, client = web(tmp_path, FakeHttp())
    download_season("batting", 2024, config=config, web=client, normalizer=FangraphsNormalizer())
    views = assert_lake_contract(config, ["fangraphs"])
    assert views.get("fangraphs_batting") == 1
