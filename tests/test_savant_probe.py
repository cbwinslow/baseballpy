"""The Savant generator's probe detects routes that ignore the season parameter."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import gen_savant_schemas as gen  # noqa: E402

from baseballpy.sources.statcast.lb_catalog import SUPPORTED  # noqa: E402

CSV = b"player_id,xba\n1,0.250\n2,0.300\n"


def test_identical_payloads_across_seasons_are_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gen, "fetch", lambda http, defn, year, min_value: CSV)
    result = gen.profile(None, SUPPORTED[0], (2022, 2023, 2024))  # type: ignore[arg-type]
    assert result["identical_years"] == [[2022, 2023, 2024]]


def test_payloads_that_differ_by_season_are_not_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    def per_year(http: object, defn: object, year: int, min_value: str | None) -> bytes:
        return CSV + f"{year},0.1\n".encode()

    monkeypatch.setattr(gen, "fetch", per_year)
    result = gen.profile(None, SUPPORTED[0], (2022, 2023))  # type: ignore[arg-type]
    assert result["identical_years"] == []
