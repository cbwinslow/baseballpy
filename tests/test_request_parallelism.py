"""Per-host in-flight limits, request-level parallelism and job prerequisites (ADR 57)."""

import asyncio
import threading
import time
from pathlib import Path

import httpx
import pytest
import respx

from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.http import HttpClient, HttpStatusError
from baseballpy.ingest.runner import run_jobs
from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job, with_needs
from baseballpy.sources.mlb_api.adapter import MlbApiAdapter
from baseballpy.sources.mlb_api.endpoints import BY_NAME, Request, prerequisites
from baseballpy.sources.mlb_api.generic import MlbEndpointExtractor

SLOW = "https://slow.example.com/r"
FAST = "https://fast.example.com/r"


def _tracker() -> tuple[dict[str, int], threading.Lock]:
    return {"active": 0, "peak": 0}, threading.Lock()


@respx.mock
def test_a_slow_host_does_not_block_a_fast_one() -> None:
    release = threading.Event()

    async def slow(request: httpx.Request) -> httpx.Response:
        while not release.is_set():
            await asyncio.sleep(0.01)
        return httpx.Response(200, content=b"slow")

    respx.get(SLOW).mock(side_effect=slow)
    respx.get(FAST).mock(return_value=httpx.Response(200, content=b"fast"))
    client = HttpClient(
        RateLimitConfig(
            max_concurrency=2,
            host_rates={"slow.example.com": 1000.0, "fast.example.com": 1000.0},
        ),
        http2=False,
    )
    holders = [
        threading.Thread(target=client.get_sync, args=(SLOW,), daemon=True) for _ in range(2)
    ]
    try:
        for thread in holders:
            thread.start()
        time.sleep(0.2)  # both slow requests now hold every slow slot
        answers: list[bytes] = []
        fast = threading.Thread(
            target=lambda: answers.append(client.get_sync(FAST).content), daemon=True
        )
        fast.start()
        fast.join(timeout=3.0)  # a shared limit would leave it waiting for the slow host
        assert answers == [b"fast"], "the fast host waited for the slow host's slots"
    finally:
        release.set()
        for thread in holders:
            thread.join(timeout=5)
        client.close()


@respx.mock
def test_per_host_limits_are_bounded_separately() -> None:
    state, lock = _tracker()
    peaks: dict[str, int] = {"a.example.com": 0, "b.example.com": 0}
    active: dict[str, int] = {"a.example.com": 0, "b.example.com": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        with lock:
            active[host] += 1
            peaks[host] = max(peaks[host], active[host])
        await asyncio.sleep(0.05)
        with lock:
            active[host] -= 1
        return httpx.Response(200, content=b"x")

    respx.get("https://a.example.com/r").mock(side_effect=handler)
    respx.get("https://b.example.com/r").mock(side_effect=handler)
    client = HttpClient(
        RateLimitConfig(
            max_concurrency=2,
            host_concurrency={"a.example.com": 5},
            host_rates={"a.example.com": 1000.0, "b.example.com": 1000.0},
        ),
        http2=False,
    )
    assert client.limit_for("a.example.com") == 5
    assert client.limit_for("b.example.com") == 2
    errors: list[BaseException] = []

    def caller(url: str) -> None:
        try:
            client.get_sync(url)
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    try:
        threads = [
            threading.Thread(target=caller, args=(f"https://{h}/r",))
            for h in ("a.example.com", "b.example.com")
            for _ in range(12)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        client.close()
    assert not errors
    assert 3 <= peaks["a.example.com"] <= 5
    assert 1 <= peaks["b.example.com"] <= 2


def _extractor(tmp_path: Path, concurrency: int = 4) -> MlbEndpointExtractor:
    http = HttpClient(
        RateLimitConfig(max_concurrency=concurrency, statsapi_rps=1000.0), http2=False
    )
    return MlbEndpointExtractor(cache_config=LakeConfig(home=tmp_path), http=http)


def _team_ctx(teams: int) -> object:
    from baseballpy.sources.mlb_api.endpoints import Context

    return Context(season=2024, team_ids=list(range(1, teams + 1)))


@respx.mock
def test_one_endpoints_requests_overlap_within_the_bound(tmp_path: Path) -> None:
    state, lock = _tracker()

    async def handler(request: httpx.Request) -> httpx.Response:
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.03)
        with lock:
            state["active"] -= 1
        return httpx.Response(200, json={"roster": []})

    respx.get(url__regex=r"https://statsapi\.mlb\.com/api/v1/teams/\d+/roster.*").mock(
        side_effect=handler
    )
    extractor = _extractor(tmp_path)
    try:
        report = extractor.ingest(BY_NAME["team_roster_active"], _team_ctx(12))  # type: ignore[arg-type]
    finally:
        extractor.http.close()
    assert report.requests == 12
    assert 2 <= state["peak"] <= 4, state


@respx.mock
def test_fail_fast_stops_queued_requests(tmp_path: Path) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("/2/roster"):
            return httpx.Response(400)
        time.sleep(0.02)
        return httpx.Response(200, json={"roster": []})

    respx.get(url__regex=r"https://statsapi\.mlb\.com/api/v1/teams/\d+/roster.*").mock(
        side_effect=handler
    )
    extractor = _extractor(tmp_path, concurrency=2)
    try:
        with pytest.raises(HttpStatusError):
            extractor.ingest(BY_NAME["team_roster_active"], _team_ctx(60))  # type: ignore[arg-type]
    finally:
        extractor.http.close()
    assert len(seen) < 30, f"queued requests kept running after the failure: {len(seen)}"


@respx.mock
def test_missing_count_is_summed_across_workers(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        team = int(request.url.path.split("/")[4])
        if team in (3, 7, 11):
            return httpx.Response(404)
        return httpx.Response(200, json={"roster": []})

    ep = BY_NAME["team_roster_active"]
    respx.get(url__regex=r"https://statsapi\.mlb\.com/api/v1/teams/\d+/roster.*").mock(
        side_effect=handler
    )
    extractor = _extractor(tmp_path)
    try:
        report = extractor.ingest(ep, _team_ctx(12))  # type: ignore[arg-type]
    finally:
        extractor.http.close()
    if ep.tolerate_missing:
        assert report.missing == 3
    else:  # a provider 404 on a non-tolerant endpoint is an error, never silently counted
        assert report.missing == 0 and len(report.errors) == 3


def test_an_empty_fan_out_is_warned_about_not_silently_completed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from baseballpy.sources.mlb_api.endpoints import Context

    extractor = _extractor(tmp_path)
    try:
        with caplog.at_level("WARNING"):
            report = extractor.ingest(BY_NAME["team_roster_active"], Context(season=2024))
    finally:
        extractor.http.close()
    assert report.requests == 0
    assert "teams_season" in caplog.text and "not in the lake" in caplog.text


def test_prerequisites_come_from_the_scope_and_the_placeholders() -> None:
    assert prerequisites(BY_NAME["team_roster_active"]) == ("teams_season",)
    assert prerequisites(BY_NAME["award_recipients"]) == ("ref_awards",)
    assert "ref_league_leader_types" in prerequisites(BY_NAME["stats_leaders"])
    assert prerequisites(BY_NAME["teams_season"]) == ()


def test_the_planner_orders_a_fan_out_endpoint_after_its_teams() -> None:
    jobs = MlbApiAdapter().plan(
        Selection(seasons=(2024,), datasets=("team_roster_active", "teams_season"))
    )
    by_name = {str(j.param("name")): j for j in jobs}
    teams = by_name["teams_season"].job_id
    assert by_name["team_roster_active"].needs == (teams,)
    assert by_name["teams_season"].needs == ()
    # a prerequisite nobody planned is read from the lake as it is
    alone = MlbApiAdapter().plan(Selection(seasons=(2024,), datasets=("team_roster_active",)))
    assert alone[0].needs == ()


class _Recorder:
    source = "t"

    def __init__(self, delay: float = 0.0, fail: set[str] | None = None) -> None:
        self.order: list[str] = []
        self.lock = threading.Lock()
        self.delay = delay
        self.fail = fail or set()

    def all_seasons(self) -> list[int]:
        return []

    def plan(self, selection: Selection) -> list[Job]:
        return []

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        time.sleep(self.delay)
        with self.lock:
            self.order.append(job.task)
        if job.task in self.fail:
            raise RuntimeError("boom")
        return JobResult(job=job, status=JobStatus.COMPLETED, rows=1)


def test_a_dependent_job_waits_for_its_prerequisite_even_with_many_workers() -> None:
    teams = make_job("t", "teams")
    roster = with_needs(make_job("t", "roster"), (teams.job_id,))
    recorder = _Recorder(delay=0.05)
    # planned in the wrong order on purpose: the dependent first
    report = run_jobs([roster, teams], {"t": recorder}, concurrency=4)  # type: ignore[dict-item]
    assert recorder.order == ["teams", "roster"]
    assert [r.status for r in report.results] == [JobStatus.COMPLETED] * 2
    assert report.results[0].job.task == "roster"  # results keep the planned order


def test_a_dependent_of_a_failed_job_fails_visibly_without_running() -> None:
    teams = make_job("t", "teams")
    roster = with_needs(make_job("t", "roster"), (teams.job_id,))
    recorder = _Recorder(fail={"teams"})
    for workers in (1, 3):
        recorder.order.clear()
        report = run_jobs([teams, roster], {"t": recorder}, concurrency=workers)  # type: ignore[dict-item]
        assert [r.status for r in report.results] == [JobStatus.FAILED, JobStatus.FAILED]
        assert "prerequisite" in (report.results[1].error or "")
        assert recorder.order == ["teams"]


def test_jobs_that_wait_for_each_other_are_rejected_before_anything_runs() -> None:
    a = make_job("t", "a")
    b = make_job("t", "b")
    jobs = [with_needs(a, (b.job_id,)), with_needs(b, (a.job_id,))]
    recorder = _Recorder()
    with pytest.raises(ValueError, match="cycle"):
        run_jobs(jobs, {"t": recorder}, concurrency=2)  # type: ignore[dict-item]
    assert recorder.order == []


def test_independent_jobs_do_run_in_parallel() -> None:
    peak = 0
    active = 0
    lock = threading.Lock()

    class Probe(_Recorder):
        def run(self, job: Job, *, refresh: bool = False) -> JobResult:
            nonlocal peak, active
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.08)
            with lock:
                active -= 1
            return JobResult(job=job, status=JobStatus.COMPLETED, rows=1)

    jobs = [make_job("t", f"j{i}") for i in range(6)]
    run_jobs(jobs, {"t": Probe()}, concurrency=3)  # type: ignore[dict-item]
    assert peak == 3


def test_the_request_shape_used_by_the_tests_is_a_real_request() -> None:
    assert Request("x", "v1/x", {}, 2024).ident == "x"


def test_savant_has_a_higher_default_in_flight_limit_than_other_hosts() -> None:
    default = HttpClient(RateLimitConfig())
    assert default.limit_for("baseballsavant.mlb.com") == 8
    assert default.limit_for("statsapi.mlb.com") == 4
    assert default.limit_for("raw.githubusercontent.com") == 4
    tuned = HttpClient(RateLimitConfig(savant_concurrency=3))
    assert tuned.limit_for("baseballsavant.mlb.com") == 3
    explicit = HttpClient(
        RateLimitConfig(host_concurrency={"baseballsavant.mlb.com": 5}, savant_concurrency=3)
    )
    assert explicit.limit_for("baseballsavant.mlb.com") == 5, "a host override wins"


def test_default_host_rates_are_the_documented_ones() -> None:
    rates = RateLimitConfig().host_rates
    assert rates["baseballsavant.mlb.com"] == 2.5
    assert rates["statsapi.mlb.com"] == 10.0
    assert rates["raw.githubusercontent.com"] == 15.0
    assert RateLimitConfig(statsapi_rps=8.0).host_rates["statsapi.mlb.com"] == 8.0
