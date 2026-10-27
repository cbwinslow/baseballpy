"""Result mapping helpers for ingestion adapters."""

from collections.abc import Iterable

from baseballpy.ingest.types import Job, JobResult, JobStatus


def counts_to_result(job: Job, counts: Iterable[int | None], detail: str = "") -> JobResult:
    """Map a collection of row counts or cache markers onto a :class:`JobResult`.

    Args:
        job: The job that produced the counts.
        counts: An iterable of row counts (integers) or ``None`` values representing
            served-from-cache results.
        detail: Optional explanatory detail for the outcome.

    Returns:
        A :class:`JobResult` with:
            - ``COMPLETED`` and ``rows=0`` if ``counts`` is empty.
            - ``SKIPPED``, ``rows=None``, and detail ``"already complete"`` (or ``detail``)
              if there is at least one count and all are ``None``.
            - ``COMPLETED`` and ``rows=sum(non_none)`` otherwise.
    """
    counts_list = list(counts)
    if not counts_list:
        return JobResult(job=job, status=JobStatus.COMPLETED, rows=0, detail=detail)

    non_none = [c for c in counts_list if c is not None]
    if not non_none:
        return JobResult(
            job=job,
            status=JobStatus.SKIPPED,
            rows=None,
            detail=detail or "already complete",
        )

    return JobResult(
        job=job,
        status=JobStatus.COMPLETED,
        rows=sum(non_none),
        detail=detail,
    )


__all__ = ["counts_to_result"]
