"""Fingerprints and the shared ``is_current`` decision (ADR 43)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.stores import RawStore
from baseballpy.core.upstream import (
    ETAG,
    GIT_BLOB,
    GIT_COMMIT,
    Fingerprint,
    is_current,
    stored_fingerprint,
)

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def _entry(fetched_ago: float = 0, **extra: Any) -> dict[str, Any]:
    stamp = (NOW - timedelta(seconds=fetched_ago)).isoformat()
    return {"status": "COMPLETED", "fetched_at": stamp, "completed_at": stamp, **extra}


def test_fingerprint_round_trip_and_comparison_ignores_origin() -> None:
    fp = Fingerprint(GIT_BLOB, "abc", origin="owner/repo:data/a.csv")
    assert Fingerprint.from_dict(fp.to_dict()) == fp
    assert fp.matches(Fingerprint(GIT_BLOB, "abc"))
    assert not fp.matches(Fingerprint(GIT_COMMIT, "abc"))
    assert not fp.matches(Fingerprint(GIT_BLOB, "abd"))
    assert Fingerprint.from_dict({"kind": "", "value": "x"}) is None
    assert Fingerprint.from_dict({"kind": "etag"}) is None


def test_stored_fingerprint_reads_upstream_then_legacy_fields() -> None:
    fp = Fingerprint(GIT_BLOB, "abc")
    assert stored_fingerprint({"upstream": fp.to_dict(), "sha": "old"}) == fp
    assert stored_fingerprint({"sha": "deadbeef"}) == Fingerprint(GIT_COMMIT, "deadbeef")
    assert stored_fingerprint({"etag": '"v1"'}) == Fingerprint(ETAG, '"v1"')
    assert stored_fingerprint({"upstream": "garbage"}) is None
    assert stored_fingerprint(None) is None


@pytest.mark.parametrize("entry", [None, {}, {"status": "FAILED"}, {"status": "ABSENT"}])
def test_missing_or_unfinished_entries_are_never_current(entry: dict[str, Any] | None) -> None:
    assert not is_current(entry, ttl_seconds=None, now=NOW)


def test_refresh_always_forces_a_fetch() -> None:
    assert not is_current(_entry(), refresh=True, ttl_seconds=None, now=NOW)


def test_expected_fingerprint_decides_without_any_time_to_live() -> None:
    wanted = Fingerprint(GIT_COMMIT, "c1")
    old = _entry(fetched_ago=10**9, upstream=wanted.to_dict())
    assert is_current(old, expected=wanted, ttl_seconds=1, now=NOW)  # age is irrelevant
    assert not is_current(old, expected=Fingerprint(GIT_COMMIT, "c2"), ttl_seconds=None, now=NOW)
    assert not is_current(_entry(), expected=wanted, ttl_seconds=None, now=NOW)  # no fingerprint


def test_time_to_live_serves_fresh_copies_without_asking_upstream() -> None:
    def probe() -> Fingerprint | None:
        raise AssertionError("a fresh copy must not trigger a request")

    assert is_current(_entry(fetched_ago=60), ttl_seconds=3600, probe=probe, now=NOW)
    assert is_current(_entry(fetched_ago=10**9), ttl_seconds=None, probe=probe, now=NOW)


def test_expired_copy_asks_upstream_and_compares() -> None:
    fp = Fingerprint(GIT_COMMIT, "c1")
    stale = _entry(fetched_ago=7200, upstream=fp.to_dict())
    confirmed: list[bool] = []
    assert is_current(
        stale,
        ttl_seconds=3600,
        probe=lambda: Fingerprint(GIT_COMMIT, "c1"),
        on_confirmed=lambda: confirmed.append(True),
        now=NOW,
    )
    assert confirmed == [True]
    assert not is_current(
        stale, ttl_seconds=3600, probe=lambda: Fingerprint(GIT_COMMIT, "c2"), now=NOW
    )
    assert not is_current(stale, ttl_seconds=3600, now=NOW)  # nothing to ask


def test_unreachable_upstream_serves_the_copy_and_says_so(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stale = _entry(fetched_ago=7200)
    with caplog.at_level("WARNING"):
        assert is_current(stale, ttl_seconds=3600, probe=lambda: None, now=NOW)
    assert "serving it" in caplog.text


def test_seasons_before_the_current_year_are_immutable() -> None:
    assert is_current(_entry(fetched_ago=10**9), ttl_seconds=60, season=2019, now=NOW)
    assert not is_current(_entry(fetched_ago=10**9), ttl_seconds=60, season=2026, now=NOW)


def test_raw_store_records_the_upstream_fingerprint_with_the_sha256(tmp_path: Path) -> None:
    raw = RawStore(LakeConfig(home=tmp_path))
    fp = Fingerprint(GIT_BLOB, "b" * 40, origin="owner/repo:data/a.csv")
    raw.put("src", "ds", "a.csv", b"x,y\n1,2\n", upstream=fp)
    raw.put("src", "ds", "b.csv", b"1", etag='"v7"')
    raw.put("src", "ds", "c.csv", b"1")
    chunks = LakeConfig(home=tmp_path).dataset_manifest("src", "ds", "raw").chunks()
    assert stored_fingerprint(chunks["a.csv"]) == fp
    assert chunks["a.csv"]["sha256"]
    assert stored_fingerprint(chunks["b.csv"]) == Fingerprint(ETAG, '"v7"')  # etag fallback
    assert stored_fingerprint(chunks["c.csv"]) is None
