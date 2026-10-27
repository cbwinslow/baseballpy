"""Tests for season selection parser in baseballpy.ingest.selection."""

import pytest

from baseballpy.ingest.selection import parse_seasons


def test_parse_single_season() -> None:
    assert parse_seasons("2023") == (2023,)


def test_parse_season_range() -> None:
    assert parse_seasons("2015-2024") == tuple(range(2015, 2025))


def test_parse_comma_separated() -> None:
    assert parse_seasons("2015,2018") == (2015, 2018)


def test_parse_mixed_ranges_and_singles() -> None:
    assert parse_seasons("2015-2017,2020") == (2015, 2016, 2017, 2020)


def test_parse_whitespace_handling() -> None:
    assert parse_seasons("  2015 - 2017 , 2020  ") == (2015, 2016, 2017, 2020)


def test_parse_sorting_and_deduplication() -> None:
    assert parse_seasons("2020,2018,2020") == (2018, 2020)
    assert parse_seasons("2015-2018,2017") == (2015, 2016, 2017, 2018)


def test_parse_all_case_insensitive_with_callback() -> None:
    def callback() -> list[int]:
        return [2021, 2019, 2020, 2021]

    assert parse_seasons("all", all_seasons=callback) == (2019, 2020, 2021)
    assert parse_seasons("ALL", all_seasons=callback) == (2019, 2020, 2021)
    assert parse_seasons("All", all_seasons=callback) == (2019, 2020, 2021)


def test_parse_all_without_callback_raises() -> None:
    with pytest.raises(ValueError, match="all_seasons callback"):
        parse_seasons("all")


@pytest.mark.parametrize("empty_input", ["", "   ", "\t\n"])
def test_parse_empty_string_raises(empty_input: str) -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_seasons(empty_input)


@pytest.mark.parametrize(
    "invalid_input",
    ["abc", "2020,abc", "2015-abc", "xyz-2020"],
)
def test_parse_non_numeric_raises(invalid_input: str) -> None:
    with pytest.raises(ValueError, match="non-numeric"):
        parse_seasons(invalid_input)


def test_parse_reversed_range_raises() -> None:
    with pytest.raises(ValueError, match="reversed season range"):
        parse_seasons("2024-2015")


@pytest.mark.parametrize(
    "malformed_range",
    ["2015-2016-2017", "-2020", "2020-", "2020,", ",2020", "2015,,2018"],
)
def test_parse_malformed_syntax_raises(malformed_range: str) -> None:
    with pytest.raises(ValueError):
        parse_seasons(malformed_range)


@pytest.mark.parametrize(
    "out_of_bounds",
    ["1799", "2101", "1700-1750", "2100-2105"],
)
def test_parse_out_of_bounds_raises(out_of_bounds: str) -> None:
    with pytest.raises(ValueError, match="1800..2100"):
        parse_seasons(out_of_bounds)


def test_parse_boundary_years_valid() -> None:
    assert parse_seasons("1800") == (1800,)
    assert parse_seasons("2100") == (2100,)
    assert parse_seasons("1800-1802") == (1800, 1801, 1802)


def test_parse_all_callback_out_of_bounds_raises() -> None:
    with pytest.raises(ValueError, match="1800..2100"):
        parse_seasons("all", all_seasons=lambda: [1799, 2020])
