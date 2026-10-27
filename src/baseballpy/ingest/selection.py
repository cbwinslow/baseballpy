"""Season expression parsing for ingestion commands and pipelines."""

from collections.abc import Callable, Sequence

MIN_SEASON = 1800
MAX_SEASON = 2100


def parse_seasons(
    text: str, all_seasons: Callable[[], Sequence[int]] | None = None
) -> tuple[int, ...]:
    """Parse a season selection expression into a sorted, unique tuple of years.

    Supported formats:
        - Single year: ``"2023"``
        - Inclusive range: ``"2015-2024"``
        - Comma-delimited list: ``"2015,2018"``
        - Mix of ranges and years: ``"2015-2017,2020"``
        - Upstream wildcard: ``"all"`` (case-insensitive, invokes ``all_seasons``)

    Args:
        text: Season specification string.
        all_seasons: Optional callback returning all available seasons for the target.

    Returns:
        Sorted tuple of validated unique integer years.

    Raises:
        ValueError: If ``text`` is empty, contains non-numeric values, invalid ranges,
            years outside 1800..2100, or ``"all"`` is passed without ``all_seasons``.
    """
    if not text or not text.strip():
        raise ValueError("seasons text cannot be empty")

    cleaned = text.strip()
    if cleaned.lower() == "all":
        if all_seasons is None:
            raise ValueError("cannot resolve 'all' seasons without an all_seasons callback")
        resolved = all_seasons()
        for y in resolved:
            if not isinstance(y, int) or y < MIN_SEASON or y > MAX_SEASON:
                raise ValueError(f"season {y} outside valid range {MIN_SEASON}..{MAX_SEASON}")
        return tuple(sorted(set(resolved)))

    parts = [p.strip() for p in cleaned.split(",")]
    seasons: set[int] = set()

    for part in parts:
        if not part:
            raise ValueError(f"invalid empty season entry in {text!r}")
        if "-" in part:
            dash_parts = part.split("-")
            if len(dash_parts) != 2:
                raise ValueError(f"invalid season range {part!r}")
            start_str, end_str = dash_parts[0].strip(), dash_parts[1].strip()
            if not start_str or not end_str:
                raise ValueError(f"invalid season range {part!r}")
            try:
                start = int(start_str)
                end = int(end_str)
            except ValueError:
                raise ValueError(f"non-numeric season in range {part!r}") from None
            if start > end:
                raise ValueError(f"reversed season range {start}-{end}; expected start <= end")
            if start < MIN_SEASON or start > MAX_SEASON:
                raise ValueError(f"season {start} outside valid range {MIN_SEASON}..{MAX_SEASON}")
            if end < MIN_SEASON or end > MAX_SEASON:
                raise ValueError(f"season {end} outside valid range {MIN_SEASON}..{MAX_SEASON}")
            for year in range(start, end + 1):
                seasons.add(year)
        else:
            try:
                year = int(part)
            except ValueError:
                raise ValueError(f"non-numeric season {part!r}") from None
            if year < MIN_SEASON or year > MAX_SEASON:
                raise ValueError(f"season {year} outside valid range {MIN_SEASON}..{MAX_SEASON}")
            seasons.add(year)

    return tuple(sorted(seasons))


__all__ = ["parse_seasons"]
