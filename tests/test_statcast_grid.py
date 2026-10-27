"""Aligned windows: overlapping, nested and adjacent requests never store a pitch twice."""

import csv
import io
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from hypothesis import given, settings
from hypothesis import strategies as st

from baseballpy.core.config import LakeConfig
from baseballpy.sources.statcast.extractor import SAVANT_BASE_URL, StatcastExtractor, grid_windows

FIXTURE = Path(__file__).parent / "fixtures" / "statcast" / "live_2024.csv"


def test_grid_windows_are_anchored_to_january_first() -> None:
    assert grid_windows(date(2024, 1, 3), date(2024, 1, 3), 5) == [
        (date(2024, 1, 1), date(2024, 1, 5))
    ]
    # 2024 is a leap year: block 18 starts on day 90 = March 31
    assert grid_windows(date(2024, 4, 1), date(2024, 4, 1), 5) == [
        (date(2024, 3, 31), date(2024, 4, 4))
    ]
    # 2025 is not: block 18 starts on day 90 = April 1
    assert grid_windows(date(2025, 4, 1), date(2025, 4, 1), 5) == [
        (date(2025, 4, 1), date(2025, 4, 5))
    ]


def test_grid_windows_never_cross_a_year_boundary() -> None:
    windows = grid_windows(date(2024, 12, 29), date(2025, 1, 3), 5)
    # 2024 has 366 days: the last block (day index 365) is the single day December 31
    assert windows[0] == (date(2024, 12, 26), date(2024, 12, 30))
    assert windows[1] == (date(2024, 12, 31), date(2024, 12, 31))
    assert windows[2][0] == date(2025, 1, 1)
    assert all(a.year == b.year for a, b in windows)


def test_grid_windows_reject_an_inverted_range() -> None:
    with pytest.raises(ValueError, match="cannot be after"):
        grid_windows(date(2024, 5, 2), date(2024, 5, 1))


@given(
    start=st.dates(min_value=date(2008, 1, 1), max_value=date(2026, 12, 31)),
    span=st.integers(min_value=0, max_value=60),
    chunk=st.integers(min_value=1, max_value=14),
    shift=st.integers(min_value=0, max_value=30),
)
@settings(max_examples=200, deadline=None)
def test_grid_windows_cover_the_range_and_agree_between_overlapping_requests(
    start: date, span: int, chunk: int, shift: int
) -> None:
    end = start + timedelta(days=span)
    windows = grid_windows(start, end, chunk)
    assert windows[0][0] <= start and windows[-1][1] >= end
    assert all(
        b + timedelta(days=1) == nxt for (_, b), (nxt, _) in zip(windows, windows[1:], strict=False)
    ), "windows are contiguous"
    # any window of another request that overlaps one of these is identical (no partial overlaps)
    other = grid_windows(
        start + timedelta(days=min(shift, span)), end + timedelta(days=shift), chunk
    )
    for w in windows:
        for o in other:
            if not (w[1] < o[0] or o[1] < w[0]):
                assert w == o


def _csv(request: httpx.Request) -> httpx.Response:
    """One pitch per day of the requested window, unique keys, dated inside the window."""
    start = date.fromisoformat(request.url.params["game_date_gt"])
    end = date.fromisoformat(request.url.params["game_date_lt"])
    rows = list(csv.reader(io.StringIO(FIXTURE.read_text("utf-8"))))
    header, template = rows[0], rows[1]
    pk, day = header.index("game_pk"), header.index("game_date")
    out = []
    current = start
    while current <= end:
        row = list(template)
        row[pk], row[day] = current.strftime("%Y%m%d"), current.isoformat()
        out.append(row)
        current += timedelta(days=1)
    buf = io.StringIO()
    csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n").writerows([header, *out])
    return httpx.Response(200, content=buf.getvalue().encode("utf-8"))


@respx.mock
def test_overlapping_nested_and_adjacent_requests_leave_no_duplicates(tmp_path: Path) -> None:
    lake = LakeConfig(home=tmp_path, today=date(2026, 1, 1))
    extractor = StatcastExtractor(cache_config=lake, chunk_days=5)
    respx.get(SAVANT_BASE_URL).mock(side_effect=_csv)
    first = extractor.extract("2024-06-10", "2024-06-16")
    nested = extractor.extract("2024-06-15", "2024-06-15")
    overlap = extractor.extract("2024-06-14", "2024-06-20")
    adjacent = extractor.extract("2024-06-17", "2024-06-19")
    day = lambda t: sorted(d.isoformat() for d in t.column("game_date").to_pylist())  # noqa: E731
    assert day(first) == [f"2024-06-{d}" for d in range(10, 17)]
    assert day(nested) == ["2024-06-15"]
    assert day(overlap) == [f"2024-06-{d}" for d in range(14, 21)]
    assert day(adjacent) == ["2024-06-17", "2024-06-18", "2024-06-19"]
    assert extractor.duplicate_keys(2024) == 0
    stored = extractor.store.read(extractor.spec, 2024)
    keys = list(
        zip(
            stored.column("game_pk").to_pylist(),
            stored.column("at_bat_number").to_pylist(),
            stored.column("pitch_number").to_pylist(),
            strict=True,
        )
    )
    assert len(keys) == len(set(keys)) == 15, "June 10..24 grid windows, each pitch once"
