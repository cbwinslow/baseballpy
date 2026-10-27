"""Tests for runner, adapters registry, and types in baseballpy.ingest."""

import threading
import time
from collections.abc import Sequence
from pathlib import Path

import pytest

from baseballpy.core.audit import AuditLogger
from baseballpy.core.config import AuditConfig
from baseballpy.ingest.adapters import (
    ADAPTERS,
    IngestAdapter,
    get_adapters,
    register_adapter,
)
from baseballpy.ingest.runner import plan_jobs, run_jobs
from baseballpy.ingest.types import (
    Job,
    JobResult,
    JobStatus,
    RunReport,
    Selection,
    make_job,
)


@pytest.fixture(autouse=True)
def clean_adapters_registry() -> None:
    """Isolate tests modifying the module-level ADAPTERS registry."""
    saved = dict(ADAPTERS)
    ADAPTERS.clear()
    yield
    ADAPTERS.clear()
    ADAPTERS.update(saved)


class FakeAdapter:
    """In-memory IngestAdapter implementation for testing."""

    def __init__(self, source: str = "fake") -> None:
        self.source = source
        self.calls: list[Job] = []

    def all_seasons(self) -> Sequence[int]:
        return [2021, 2022, 2023]

    def plan(self, selection: Selection) -> list[Job]:
        seasons = selection.seasons or (2023,)
        return [make_job(self.source, "season", season=s) for s in seasons]

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        self.calls.append(job)
        return JobResult(job=job, status=JobStatus.COMPLETED, rows=10, seconds=0.01)


def test_job_types_and_helpers() -> None:
    assert JobStatus.PLANNED == "planned"
    assert JobStatus.COMPLETED == "completed"
    assert JobStatus.SKIPPED == "skipped"
    assert JobStatus.FAILED == "failed"
    assert JobStatus.CANCELLED == "cancelled"

    job = make_job("statcast", "season", season=2023, dataset="pitches")
    assert job.job_id == "statcast:season:dataset=pitches:season=2023"
    assert job.param("season") == 2023
    assert job.param("dataset") == "pitches"
    assert job.param("absent") is None
    assert job.param("absent", default="fallback") == "fallback"

    simple_job = Job("lahman", "people")
    assert simple_job.job_id == "lahman:people"

    sel = Selection(seasons=(2022, 2023), sources=("statcast",), refresh=True)
    assert sel.seasons == (2022, 2023)
    assert sel.refresh is True

    res1 = JobResult(job=job, status=JobStatus.COMPLETED, rows=100)
    res2 = JobResult(job=simple_job, status=JobStatus.FAILED, error="bad")
    report = RunReport(results=[res1, res2])
    assert report.failed == [res2]
    assert report.cancelled == []
    assert report.exit_code == 1
    assert report.counts() == {"completed": 1, "failed": 1}


def test_registry_registration_and_lazy_instantiation() -> None:
    factory_calls = {"a": 0, "b": 0}

    def factory_a() -> IngestAdapter:
        factory_calls["a"] += 1
        return FakeAdapter("source_a")

    def factory_b() -> IngestAdapter:
        factory_calls["b"] += 1
        return FakeAdapter("source_b")

    register_adapter("source_a", factory_a)
    register_adapter("source_b", factory_b)

    # Re-registering with the exact same factory is a no-op
    register_adapter("source_a", factory_a)

    # Registering a duplicate source with a different factory raises ValueError
    with pytest.raises(ValueError, match="already registered"):
        register_adapter("source_a", lambda: FakeAdapter("other"))

    # Registering does not instantiate
    assert factory_calls["a"] == 0
    assert factory_calls["b"] == 0

    # Asking for a specific source instantiates only that source
    adapters = get_adapters(["source_a"])
    assert "source_a" in adapters
    assert factory_calls["a"] == 1
    assert factory_calls["b"] == 0

    # Asking for unknown source raises KeyError listing known sources
    with pytest.raises(KeyError, match="known: source_a, source_b"):
        get_adapters(["nonexistent"])

    # Empty sources instantiates all
    all_adapters = get_adapters()
    assert set(all_adapters.keys()) == {"source_a", "source_b"}
    assert factory_calls["a"] == 2
    assert factory_calls["b"] == 1


def test_plan_jobs_sorted_source_order() -> None:
    adapters = {
        "statcast": FakeAdapter("statcast"),
        "chadwick": FakeAdapter("chadwick"),
    }
    sel = Selection(seasons=(2022, 2023))
    jobs = plan_jobs(adapters, sel)
    # Sorted order: chadwick first, then statcast
    assert [j.source for j in jobs] == ["chadwick", "chadwick", "statcast", "statcast"]
    assert [j.param("season") for j in jobs] == [2022, 2023, 2022, 2023]


def test_run_jobs_keeps_input_order() -> None:
    class DelayAdapter(FakeAdapter):
        def run(self, job: Job, *, refresh: bool = False) -> JobResult:
            idx = int(job.param("idx", 0) or 0)
            # Sleep inversely to index so later jobs finish faster
            time.sleep(0.002 * (5 - idx))
            return JobResult(job=job, status=JobStatus.COMPLETED, rows=idx, seconds=0.01)

    adapters = {"delay": DelayAdapter("delay")}
    jobs = [make_job("delay", "unit", idx=i) for i in range(5)]
    report = run_jobs(jobs, adapters, concurrency=3)

    assert [r.job.param("idx") for r in report.results] == list(range(5))
    assert report.exit_code == 0


def test_run_jobs_concurrency_overlap() -> None:
    barrier = threading.Barrier(2)

    class BarrierAdapter(FakeAdapter):
        def run(self, job: Job, *, refresh: bool = False) -> JobResult:
            # Both threads must reach this barrier concurrently
            barrier.wait(timeout=1.0)
            return JobResult(job=job, status=JobStatus.COMPLETED, rows=1)

    adapters = {"barrier": BarrierAdapter("barrier")}
    jobs = [make_job("barrier", "t", id=1), make_job("barrier", "t", id=2)]
    report = run_jobs(jobs, adapters, concurrency=2)
    assert len(report.results) == 2
    assert report.exit_code == 0


def test_run_jobs_failed_collected_and_run_continues() -> None:
    class FailingAdapter(FakeAdapter):
        def run(self, job: Job, *, refresh: bool = False) -> JobResult:
            if job.param("id") == 2:
                raise RuntimeError("something went wrong")
            return JobResult(job=job, status=JobStatus.COMPLETED, rows=5)

    adapters = {"failing": FailingAdapter("failing")}
    jobs = [make_job("failing", "task", id=i) for i in (1, 2, 3)]
    report = run_jobs(jobs, adapters, continue_on_error=True)

    assert len(report.results) == 3
    assert report.results[0].status == JobStatus.COMPLETED
    assert report.results[1].status == JobStatus.FAILED
    assert "RuntimeError: something went wrong" in (report.results[1].error or "")
    assert report.results[2].status == JobStatus.COMPLETED
    assert report.exit_code == 1


def test_run_jobs_continue_on_error_false_reraises() -> None:
    class FatalAdapter(FakeAdapter):
        def run(self, job: Job, *, refresh: bool = False) -> JobResult:
            raise ValueError("stop immediately")

    adapters = {"fatal": FatalAdapter("fatal")}
    jobs = [make_job("fatal", "task", id=1)]

    with pytest.raises(ValueError, match="stop immediately"):
        run_jobs(jobs, adapters, continue_on_error=False)


def test_run_jobs_missing_adapter_records_failed() -> None:
    jobs = [make_job("unknown_source", "task", id=1)]
    report = run_jobs(jobs, adapters={}, continue_on_error=False)

    assert len(report.results) == 1
    assert report.results[0].status == JobStatus.FAILED
    assert "no adapter for source unknown_source" in (report.results[0].error or "")
    assert report.exit_code == 1


def test_run_jobs_keyboard_interrupt_marks_cancelled() -> None:
    class InterruptAdapter(FakeAdapter):
        def run(self, job: Job, *, refresh: bool = False) -> JobResult:
            if job.param("fail") is True:
                raise KeyboardInterrupt("Simulated Ctrl-C")
            return JobResult(job=job, status=JobStatus.COMPLETED, rows=1)

    adapters = {"intr": InterruptAdapter("intr")}
    jobs = [
        make_job("intr", "task", fail=False, id=1),
        make_job("intr", "task", fail=True, id=2),
        make_job("intr", "task", fail=False, id=3),
    ]
    report = run_jobs(jobs, adapters, concurrency=1)

    assert report.exit_code == 130
    assert len(report.results) == 3
    assert report.results[0].status == JobStatus.COMPLETED
    assert report.results[1].status == JobStatus.CANCELLED
    assert report.results[2].status == JobStatus.CANCELLED


def test_run_jobs_concurrency_validation() -> None:
    with pytest.raises(ValueError, match="concurrency must be at least 1"):
        run_jobs([], {}, concurrency=0)


def test_run_jobs_writes_audit_events(tmp_path: Path) -> None:
    config = AuditConfig(log_dir_override=tmp_path)
    logger = AuditLogger(config)

    adapters = {"fake": FakeAdapter("fake")}
    jobs = [make_job("fake", "season", season=2023)]
    report = run_jobs(jobs, adapters, audit=logger)

    assert report.exit_code == 0
    events = logger.read_events()
    assert len(events) == 1
    assert events[0].operation == "ingest_job"
    assert events[0].source == "fake"
    assert events[0].endpoint == "fake:season:season=2023"
