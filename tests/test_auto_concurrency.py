from unittest.mock import patch

import pytest

from baseballpy.core.concurrency import (
    DEFAULT_MAX_CONCURRENCY_CAP,
    resolve_concurrency,
)
from baseballpy.ingest.adapters import IngestAdapter
from baseballpy.ingest.runner import run_jobs
from baseballpy.ingest.types import Job, JobResult, JobStatus


def test_resolve_concurrency_explicit_integer() -> None:
    assert resolve_concurrency(1) == 1
    assert resolve_concurrency(4) == 4
    assert resolve_concurrency(16) == 16
    assert resolve_concurrency("8") == 8


def test_resolve_concurrency_invalid_values() -> None:
    with pytest.raises(ValueError, match="concurrency must be at least 1"):
        resolve_concurrency(0)

    with pytest.raises(ValueError, match="concurrency must be at least 1"):
        resolve_concurrency(-5)

    with pytest.raises(ValueError, match="concurrency must be an integer >= 1 or 'auto'"):
        resolve_concurrency("invalid")

    with pytest.raises(ValueError, match="concurrency must be an integer >= 1 or 'auto'"):
        resolve_concurrency("")


def test_resolve_concurrency_auto_scaling() -> None:
    # Test on simulated 2-core machine
    with patch("os.cpu_count", return_value=2):
        assert resolve_concurrency(None) == 2
        assert resolve_concurrency("auto") == 2
        assert resolve_concurrency("AUTO") == 2

    # Test on simulated 8-core machine
    with patch("os.cpu_count", return_value=8):
        assert resolve_concurrency(None) == 8
        assert resolve_concurrency("auto") == 8

    # Test on simulated 56-core workstation (capped at DEFAULT_MAX_CONCURRENCY_CAP=32)
    with patch("os.cpu_count", return_value=56):
        assert resolve_concurrency(None) == DEFAULT_MAX_CONCURRENCY_CAP
        assert resolve_concurrency("auto") == DEFAULT_MAX_CONCURRENCY_CAP

    # Test when cpu_count returns None (fallback to 4)
    with patch("os.cpu_count", return_value=None):
        assert resolve_concurrency(None) == 4


def test_resolve_concurrency_bounded_by_job_count() -> None:
    with patch("os.cpu_count", return_value=56):
        # Even with 56 cores, if we only have 3 jobs, resolve to 3 workers
        assert resolve_concurrency(None, job_count=3) == 3
        # If we have 50 jobs, cap at 32
        assert resolve_concurrency(None, job_count=50) == 32
        # Explicit override takes precedence over job count
        assert resolve_concurrency(1, job_count=50) == 1


class DummyAdapter(IngestAdapter):
    source = "dummy"

    def plan(self, selection: object) -> list[Job]:
        return []

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        return JobResult(job=job, status=JobStatus.COMPLETED, rows=1)


def test_run_jobs_accepts_auto_and_none() -> None:
    job = Job(source="dummy", task="test", params=(("id", 1),))
    adapters = {"dummy": DummyAdapter()}

    # Calling run_jobs with concurrency=None (default) works
    report = run_jobs([job], adapters, concurrency=None)
    assert len(report.results) == 1
    assert report.results[0].status == JobStatus.COMPLETED

    # Calling run_jobs with concurrency="auto" works
    report2 = run_jobs([job], adapters, concurrency="auto")
    assert len(report2.results) == 1
    assert report2.results[0].status == JobStatus.COMPLETED
