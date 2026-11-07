"""A host limited to less than one request a second (Baseball-Reference allows 20 a minute)."""

import pytest

from baseballpy.core.config import BREF_HOST, RateLimitConfig
from baseballpy.core.http import HttpClient


def test_a_rate_below_one_per_second_is_one_request_per_interval() -> None:
    client = HttpClient(RateLimitConfig(host_rates={"slow.example": 0.25}))
    limiter = client._limiter_for("slow.example")  # noqa: SLF001 - the bucket is what is tested
    assert limiter.max_rate == 1 and limiter.time_period == pytest.approx(4.0)
    fast = client._limiter_for("fast.example")  # noqa: SLF001
    assert fast.max_rate == pytest.approx(RateLimitConfig().default_requests_per_second)


def test_baseball_reference_is_far_below_the_documented_block_threshold() -> None:
    config = RateLimitConfig()
    per_minute = config.host_rates[BREF_HOST] * 60
    assert per_minute <= 6 < 20, "Sports Reference blocks a session above 20 requests a minute"
    assert config.host_concurrency[BREF_HOST] == 1


def test_baseball_reference_is_never_retried_after_a_refusal() -> None:
    config = RateLimitConfig()
    assert config.host_max_attempts[BREF_HOST] == 1 < config.max_retries
