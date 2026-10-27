"""Ingestion core: job types, selection parser, adapter Protocol and registry, and runner."""

from baseballpy.ingest.adapters import (
    ADAPTERS,
    IngestAdapter,
    get_adapters,
    register_adapter,
)
from baseballpy.ingest.runner import plan_jobs, run_jobs
from baseballpy.ingest.selection import parse_seasons
from baseballpy.ingest.types import (
    Job,
    JobResult,
    JobStatus,
    RunReport,
    Selection,
    make_job,
)

__all__ = [
    "ADAPTERS",
    "IngestAdapter",
    "Job",
    "JobResult",
    "JobStatus",
    "RunReport",
    "Selection",
    "get_adapters",
    "make_job",
    "parse_seasons",
    "plan_jobs",
    "register_adapter",
    "run_jobs",
]
