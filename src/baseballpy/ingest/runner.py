"""Ingestion plan and run orchestrators."""

import concurrent.futures
import logging
import time
from collections.abc import Mapping, Sequence

from baseballpy.core.audit import AuditLogger, default_audit_logger
from baseballpy.ingest.adapters import IngestAdapter
from baseballpy.ingest.types import Job, JobResult, JobStatus, RunReport, Selection

logger = logging.getLogger(__name__)


def plan_jobs(adapters: Mapping[str, IngestAdapter], selection: Selection) -> list[Job]:
    """Concatenate planned jobs across adapters in sorted source order.

    Performs no network or disk I/O of its own.
    """
    sources = sorted(adapters.keys())
    if selection.sources:
        sources = [s for s in sources if s in selection.sources]
    planned: list[Job] = []
    for source in sources:
        planned.extend(adapters[source].plan(selection))
    return planned


def run_jobs(
    jobs: Sequence[Job],
    adapters: Mapping[str, IngestAdapter],
    *,
    refresh: bool = False,
    concurrency: int = 1,
    continue_on_error: bool = True,
    audit: AuditLogger | None = None,
) -> RunReport:
    """Execute jobs with bounded concurrency, structured audit logging, and error handling.

    Args:
        jobs: Sequence of jobs to execute in order.
        adapters: Mapping from source name to adapter instance.
        refresh: Whether to force fresh downloads, ignoring cached data.
        concurrency: Max worker threads (must be >= 1).
        continue_on_error: If True, failures are recorded and execution continues;
            if False, exceptions are re-raised immediately.
        audit: Optional audit logger; defaults to :data:`default_audit_logger`.

    Returns:
        :class:`RunReport` containing all job results in input order.

    Raises:
        ValueError: If ``concurrency < 1``.
        Exception: If ``continue_on_error`` is False and any job raises.
    """
    if concurrency < 1:
        raise ValueError(f"concurrency must be at least 1; got {concurrency}")

    if not jobs:
        return RunReport()

    audit_logger = audit if audit is not None else default_audit_logger

    def _run_single(job: Job) -> JobResult:
        start = time.perf_counter()
        try:
            with audit_logger.track(
                operation="ingest_job",
                source=job.source,
                endpoint=job.job_id,
            ) as tracker:
                adapter = adapters.get(job.source)
                if adapter is None:
                    duration = time.perf_counter() - start
                    msg = f"no adapter for source {job.source}"
                    tracker.error = msg
                    return JobResult(
                        job=job,
                        status=JobStatus.FAILED,
                        seconds=round(duration, 4),
                        detail=msg,
                        error=msg,
                    )
                result = adapter.run(job, refresh=refresh)
                duration = time.perf_counter() - start
                if result.seconds == 0.0:
                    result.seconds = round(duration, 4)
                if result.rows is not None:
                    tracker.set_records(result.rows)
                return result
        except Exception as exc:
            duration = time.perf_counter() - start
            logger.exception("Job %s failed: %s", job.job_id, exc)
            if not continue_on_error:
                raise
            return JobResult(
                job=job,
                status=JobStatus.FAILED,
                seconds=round(duration, 4),
                detail=str(exc),
                error=f"{type(exc).__name__}: {exc}",
            )

    results: list[JobResult | None] = [None] * len(jobs)
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)
    futures: list[concurrent.futures.Future[JobResult]] = []
    future_to_index: dict[concurrent.futures.Future[JobResult], int] = {}

    try:
        for idx, job in enumerate(jobs):
            fut = executor.submit(_run_single, job)
            futures.append(fut)
            future_to_index[fut] = idx

        for fut in concurrent.futures.as_completed(futures):
            idx = future_to_index[fut]
            results[idx] = fut.result()
    except KeyboardInterrupt:
        for fut in futures:
            fut.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
        for k, job in enumerate(jobs):
            if results[k] is None:
                results[k] = JobResult(
                    job=job,
                    status=JobStatus.CANCELLED,
                    detail="cancelled",
                )
        return RunReport(results=[r for r in results if r is not None])
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    return RunReport(results=[r for r in results if r is not None])


__all__ = ["plan_jobs", "run_jobs"]
