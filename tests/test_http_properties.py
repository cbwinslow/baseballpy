"""Property-based tests for the HTTP retry helpers in ``baseballpy.core.http``.

Two real defects of ``_parse_retry_after`` were found by these properties (2026-11-14) and fixed:

* ``"nan"`` parsed as a float and escaped the ``min``/``max`` clamp (every comparison with NaN is False), so
  the result was NaN and the later sleep would raise; it is now ``None``.
* on Windows a timezone-less HTTP date before 1970 raised ``OSError`` from ``datetime.timestamp()``; a date
  without a zone is now read as GMT and an unrepresentable date gives ``None``.
"""

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st
from tenacity import RetryCallState, wait_exponential_jitter

from baseballpy.core.http import (
    MAX_RETRY_AFTER_SECONDS,
    RETRYABLE_STATUSES,
    SLOWDOWN_STATUSES,
    HttpStatusError,
    RetryableStatus,
    _parse_retry_after,
)

SETTINGS = settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

MAX_BACKOFF_SECONDS = 60.0

ARBITRARY_RETRY_AFTER = st.one_of(st.text(max_size=24), st.none())

DATE_LIKE_RETRY_AFTER = st.builds(
    lambda year, suffix: f"1 Jan {year} 00:00{suffix}",
    st.sampled_from(("1950", "1969", "68", "69", "2024")),
    st.sampled_from(("", " GMT", " +0000")),
)

NON_NEGATIVE_NUMBER = st.one_of(
    st.integers(min_value=0, max_value=10**15).map(str),
    st.floats(min_value=0.0, max_value=10**15, allow_nan=False, allow_infinity=False).map(repr),
)

NEGATIVE_NUMBER = st.one_of(
    st.integers(max_value=-1).map(str),
    st.floats(min_value=-(10**15), max_value=-1e-9, allow_nan=False, allow_infinity=False).map(
        repr
    ),
    st.just("-inf"),
)

SECONDS_FROM_NOW = st.integers(min_value=1, max_value=10**9)

BACKOFF_MULTIPLIER = st.floats(
    min_value=0.001, max_value=2.0, allow_nan=False, allow_infinity=False
)
BACKOFF_ATTEMPT = st.integers(min_value=1, max_value=30)


def test_slowdown_statuses_are_a_subset_of_retryable() -> None:
    """SLOWDOWN_STATUSES ⊆ RETRYABLE_STATUSES and 408/425/500/502/504 are not slowdowns."""
    assert SLOWDOWN_STATUSES <= RETRYABLE_STATUSES
    assert {429, 503} <= SLOWDOWN_STATUSES
    assert not SLOWDOWN_STATUSES & {408, 425, 500, 502, 504}


@given(status=st.integers(), retry_after=st.one_of(st.none(), st.floats(allow_nan=False)))
@SETTINGS
def test_retryable_status_keeps_status_and_retry_after(
    status: int, retry_after: float | None
) -> None:
    """RetryableStatus stores the status and retry_after it was given, unchanged."""
    exc = RetryableStatus(status, retry_after=retry_after)
    assert exc.status == status
    assert exc.retry_after == retry_after


@given(url=st.text(max_size=30), status=st.integers())
@SETTINGS
def test_http_status_error_keeps_url_and_status(url: str, status: int) -> None:
    """HttpStatusError stores the url and status it was given, unchanged."""
    exc = HttpStatusError(url, status)
    assert exc.url == url
    assert exc.status == status


@given(
    value=st.one_of(
        st.none(),
        st.text(alphabet=" \t\n\r\v\f\x1c\x85\xa0", max_size=8),
    )
)
@SETTINGS
def test_blank_or_none_value_returns_none(value: str | None) -> None:
    """Blank whitespace-only text and None are reported as None."""
    assert _parse_retry_after(value) is None


@example(value="1 Jan 1950 0:0")
@given(value=st.one_of(ARBITRARY_RETRY_AFTER, DATE_LIKE_RETRY_AFTER))
@SETTINGS
def test_parse_retry_after_never_raises(value: str | None) -> None:
    """For any text or None, _parse_retry_after returns instead of raising."""
    _parse_retry_after(value)


@example(value="nan")
@given(value=ARBITRARY_RETRY_AFTER)
@SETTINGS
def test_parse_retry_after_result_is_none_or_bounded(value: str | None) -> None:
    """The result is None or a float in [0.0, MAX_RETRY_AFTER_SECONDS]."""
    result = _parse_retry_after(value)
    assert result is None or (
        isinstance(result, float) and 0.0 <= result <= MAX_RETRY_AFTER_SECONDS
    )


@given(value=NON_NEGATIVE_NUMBER)
@SETTINGS
def test_non_negative_number_is_capped_not_shifted(value: str) -> None:
    """A non-negative number string maps to min(float(value), MAX_RETRY_AFTER_SECONDS)."""
    result = _parse_retry_after(value)
    assert result == min(float(value), MAX_RETRY_AFTER_SECONDS)
    assert 0.0 <= result <= MAX_RETRY_AFTER_SECONDS


@given(value=NEGATIVE_NUMBER)
@SETTINGS
def test_negative_number_clamps_to_zero(value: str) -> None:
    """A negative number string clamps to 0.0 instead of producing a negative wait."""
    assert _parse_retry_after(value) == 0.0


@given(seconds_ago=st.integers(min_value=2, max_value=10**9))
@SETTINGS
def test_past_http_date_returns_zero(seconds_ago: int) -> None:
    """An expired HTTP-date clamps to exactly 0.0."""
    stamp = datetime.now(UTC) - timedelta(seconds=seconds_ago)
    result = _parse_retry_after(format_datetime(stamp, usegmt=True))
    assert result == 0.0


@given(seconds_from_now=SECONDS_FROM_NOW)
@SETTINGS
def test_future_http_date_is_bounded_by_cap(seconds_from_now: int) -> None:
    """A future HTTP-date yields a wait in [0, cap], equal to the cap once it is far enough."""
    stamp = datetime.now(UTC) + timedelta(seconds=seconds_from_now)
    result = _parse_retry_after(format_datetime(stamp, usegmt=True))
    assert 0.0 <= result <= MAX_RETRY_AFTER_SECONDS
    if seconds_from_now >= 180:
        assert result == MAX_RETRY_AFTER_SECONDS


@given(multiplier=BACKOFF_MULTIPLIER, attempt_number=BACKOFF_ATTEMPT)
@SETTINGS
def test_exponential_backoff_respects_bounds(multiplier: float, attempt_number: int) -> None:
    """wait_exponential_jitter(multiplier=m, max=60) stays in [m*2**(n-1), 60.0].

    tenacity 9.x adds the jitter before the cap, so the upper bound is exactly
    the ``max`` argument, not ``max + jitter``.
    """
    state = RetryCallState(None, None, (), {})
    state.attempt_number = attempt_number
    wait = float(wait_exponential_jitter(multiplier=multiplier, max=MAX_BACKOFF_SECONDS)(state))
    assert 0.0 <= wait <= MAX_BACKOFF_SECONDS
    assert wait >= min(multiplier * 2.0 ** (attempt_number - 1), MAX_BACKOFF_SECONDS)
