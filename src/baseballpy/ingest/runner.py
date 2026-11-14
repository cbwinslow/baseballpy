"""Ingestion plan and run orchestrators."""

import concurrent.futures
import logging
import time
from collections.abc import Callable, Mapping, Sequence

from baseballpy.core.audit import AuditLogger, default_audit_logger
from baseballpy.core.concurrency import resolve_concurrency
from baseballpy.core.memguard import MemoryGovernor
from baseballpy.ingest.adapters import IngestAdapter
from baseballpy.ingest.types import Job, JobResult, JobStatus, RunReport, Selection

logger = logging.getLogger(__name__)

POLL_SECONDS = 0.2


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
    concurrency: int | str | None = None,
    continue_on_error: bool = True,
    audit: AuditLogger | None = None,
    governor: MemoryGovernor | None = None,
) -> RunReport:
    """Execute jobs with bounded concurrency, structured audit logging, and error handling.

    Args:
        jobs: Sequence of jobs to execute in order.
        adapters: Mapping from source name to adapter instance.
        refresh: Whether to force fresh downloads, ignoring cached data.
        concurrency: Max worker threads (integer >= 1, ``"auto"``, or ``None`` for auto-detect).
        continue_on_error: If True, failures are recorded and execution continues;
            if False, exceptions are re-raised immediately.
        audit: Optional audit logger; defaults to :data:`default_audit_logger`.
        governor: Decides from live, measured memory whether one more job may start (default: a new
            :class:`MemoryGovernor`); ``concurrency`` is only the upper bound.

    Returns:
        :class:`RunReport` containing all job results in input order.

    Raises:
        ValueError: If ``concurrency < 1`` or unparseable.
        Exception: If ``continue_on_error`` is False and any job raises.
    """
    workers = resolve_concurrency(concurrency, job_count=len(jobs))

    if not jobs:
        return RunReport()

    audit_logger = audit if audit is not None else default_audit_logger

    def _run_single(job: Job, blocked_by: str | None = None) -> JobResult:
        return _run_one(
            job, blocked_by, adapters, audit_logger,
            refresh=refresh, continue_on_error=continue_on_error,
        )  # fmt: skip

    results: list[JobResult | None] = [None] * len(jobs)
    deps = _dependencies(jobs)
    interrupted = False
    try:
        if workers == 1:
            # In the calling thread, so Ctrl-C reaches the running job's blocking I/O directly.
            for idx in _order(jobs, deps):
                results[idx] = _run_single(jobs[idx], _blocker(jobs, deps[idx], results))
        else:
            _run_pool(
                jobs,
                _run_single,
                workers,
                results,
                deps,
                governor or MemoryGovernor(),
                audit_logger,
            )
    except KeyboardInterrupt:
        interrupted = True
    if interrupted:
        for k, job in enumerate(jobs):
            if results[k] is None:
                results[k] = JobResult(job=job, status=JobStatus.CANCELLED, detail="cancelled")
    return RunReport(results=[r for r in results if r is not None])


def _run_one(
    job: Job,
    blocked_by: str | None,
    adapters: Mapping[str, IngestAdapter],
    audit_logger: AuditLogger,
    *,
    refresh: bool,
    continue_on_error: bool,
) -> JobResult:
    """Run one job under an audit record; a failure becomes a FAILED result unless told to raise."""
    start = time.perf_counter()
    try:
        with audit_logger.track(
            operation="ingest_job", source=job.source, endpoint=job.job_id
        ) as tracker:
            if blocked_by is not None:
                # its input would be missing or stale: fail visibly instead of storing nothing
                msg = f"not run: prerequisite job {blocked_by} did not finish"
                tracker.error = msg
                return JobResult(job=job, status=JobStatus.FAILED, detail=msg, error=msg)
            adapter = adapters.get(job.source)
            if adapter is None:
                msg = f"no adapter for source {job.source}"
                tracker.error = msg
                seconds = round(time.perf_counter() - start, 4)
                return JobResult(
                    job=job, status=JobStatus.FAILED, seconds=seconds, detail=msg, error=msg
                )
            result = adapter.run(job, refresh=refresh)
            if result.seconds == 0.0:
                result.seconds = round(time.perf_counter() - start, 4)
            if result.rows is not None:
                tracker.set_records(result.rows)
            if result.cache_hit:
                tracker.set_cache_hit(True)
            return result
    except Exception as exc:
        logger.exception("Job %s failed: %s", job.job_id, exc)
        if not continue_on_error:
            raise
        return JobResult(
            job=job,
            status=JobStatus.FAILED,
            seconds=round(time.perf_counter() - start, 4),
            detail=str(exc),
            error=f"{type(exc).__name__}: {exc}",
        )


def _dependencies(jobs: Sequence[Job]) -> list[list[int]]:
    """For each job, the indexes of the planned jobs it needs (a need not in the plan is ignored)."""
    index = {job.job_id: i for i, job in enumerate(jobs)}
    return [
        [index[n] for n in job.needs if n in index and index[n] != i] for i, job in enumerate(jobs)
    ]


def _order(jobs: Sequence[Job], deps: Sequence[Sequence[int]]) -> list[int]:
    """Planned order with every job after the jobs it needs; raises if jobs wait for each other."""
    ordered: list[int] = []
    done: set[int] = set()
    waiting = list(range(len(jobs)))
    while waiting:
        ready = [i for i in waiting if all(d in done for d in deps[i])]
        if not ready:
            names = ", ".join(jobs[i].job_id for i in waiting)
            raise ValueError(f"jobs wait for each other (cycle): {names}")
        first = ready[0]
        ordered.append(first)
        done.add(first)
        waiting.remove(first)
    return ordered


def _blocker(
    jobs: Sequence[Job], needs: Sequence[int], results: Sequence[JobResult | None]
) -> str | None:
    """``job_id`` of a needed job that failed or was cancelled, if any."""
    for dep in needs:
        result = results[dep]
        if result is not None and result.status in (JobStatus.FAILED, JobStatus.CANCELLED):
            return jobs[dep].job_id
    return None


def _log_hold(
    governor: MemoryGovernor, running: int, waiting: int, audit_logger: AuditLogger | None
) -> None:
    """Say, in the log and the audit record, that jobs are held back for memory and why."""
    text = f"{waiting} job(s) wait while {running} run: {governor.status()}"
    logger.warning("memory: %s", text)
    if audit_logger is not None:
        with audit_logger.track(operation="memory_hold", source="ingest", endpoint=text) as tracker:
            tracker.set_records(waiting)


def _run_pool(
    jobs: Sequence[Job],
    run_single: Callable[[Job, str | None], JobResult],
    concurrency: int,
    results: list[JobResult | None],
    deps: Sequence[Sequence[int]],
    governor: MemoryGovernor | None = None,
    audit_logger: AuditLogger | None = None,
) -> None:
    """Run ``jobs`` on a thread pool, filling ``results`` by input index as they finish.

    A job starts only when the jobs it needs have finished; one whose prerequisite failed is
    reported failed without running. The main thread polls with a short timeout: on Windows a
    blocking wait on a lock is not interrupted by Ctrl-C, a timed one is. On ``KeyboardInterrupt``
    queued jobs are dropped and the exception propagates; jobs already running finish their
    current call (threads cannot be killed) before the interpreter exits.
    """
    _order(jobs, deps)  # fail on a cycle before anything runs
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)
    waiting = {i: set(d) for i, d in enumerate(deps)}
    running: dict[concurrent.futures.Future[JobResult], int] = {}

    held_logged = False

    def submit_ready() -> None:
        nonlocal held_logged
        for idx in sorted(i for i, needs in waiting.items() if not needs):
            if len(running) >= concurrency:
                return  # every worker has a job: a queued job is not "running" (the memory guard counts them)
            if governor is not None and running and not governor.may_start(len(running)):
                if not held_logged:  # one line when a hold begins, not one per poll
                    held_logged = True
                    _log_hold(governor, len(running), len(waiting), audit_logger)
                return
            held_logged = False
            del waiting[idx]
            blocked = _blocker(jobs, deps[idx], results)
            running[executor.submit(run_single, jobs[idx], blocked)] = idx
            if governor is not None:
                governor.note_started()

    submit_ready()
    try:
        while running:
            done, _ = concurrent.futures.wait(
                running, timeout=POLL_SECONDS, return_when=concurrent.futures.FIRST_COMPLETED
            )
            if governor is not None:
                governor.observe(len(running))
            for fut in done:
                idx = running.pop(fut)
                results[idx] = fut.result()
                for needs in waiting.values():
                    needs.discard(idx)
            submit_ready()
    except BaseException:
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    executor.shutdown(wait=True)


__all__ = ["plan_jobs", "run_jobs"]
