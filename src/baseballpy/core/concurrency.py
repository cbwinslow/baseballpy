"""Centralized concurrency utilities for baseballpy.

Calculates optimal worker thread bounds dynamically based on CPU core counts
and planned workload size while preserving user overrides and safety invariants.
"""

from __future__ import annotations

import os

#: Default maximum concurrency cap to prevent socket exhaustion and excessive memory use.
DEFAULT_MAX_CONCURRENCY_CAP = 32

#: Minimum safe concurrency floor.
MIN_CONCURRENCY = 1


def resolve_concurrency(
    concurrency: int | str | None = None,
    job_count: int | None = None,
    *,
    max_cap: int = DEFAULT_MAX_CONCURRENCY_CAP,
) -> int:
    """Resolve the effective worker thread count.

    If ``concurrency`` is ``None`` or ``"auto"`` (case-insensitive), dynamically calculates
    the worker pool size using system CPU core count bounded by ``max_cap`` and ``job_count``:
    - Scales with ``max(2, os.cpu_count() or 4)``
    - Capped at ``max_cap`` (default 32)
    - If ``job_count`` is given and > 0, bounded by ``job_count`` (no redundant idle threads)

    Args:
        concurrency: An integer >= 1, ``None``, or the string ``"auto"``.
        job_count: Optional count of planned jobs to bound maximum worker allocation.
        max_cap: Maximum upper bound for auto-calculated concurrency (default: 32).

    Returns:
        Effective integer worker thread count >= 1.

    Raises:
        ValueError: If ``concurrency`` is an invalid string or integer < 1.
    """
    if concurrency is None or (
        isinstance(concurrency, str) and concurrency.strip().lower() == "auto"
    ):
        cpus = os.cpu_count() or 4
        # Standard I/O worker heuristic: at least 2 workers, up to cpus, capped at max_cap
        target = min(max_cap, max(2, cpus))
        if job_count is not None and job_count > 0:
            return min(target, job_count)
        return target

    try:
        val = int(concurrency)
    except (ValueError, TypeError):
        raise ValueError(
            f"concurrency must be an integer >= 1 or 'auto'; got {concurrency!r}"
        ) from None

    if val < MIN_CONCURRENCY:
        raise ValueError(f"concurrency must be at least 1; got {val}")

    return val


__all__ = ["DEFAULT_MAX_CONCURRENCY_CAP", "MIN_CONCURRENCY", "resolve_concurrency"]
