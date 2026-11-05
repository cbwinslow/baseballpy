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
            _check_range(y)
        return tuple(sorted(set(resolved)))

    seasons: set[int] = set()
    for part in (p.strip() for p in cleaned.split(",")):
        if not part:
            raise ValueError(f"invalid empty season entry in {text!r}")
        seasons.update(_expand(part))
    return tuple(sorted(seasons))


def _check_range(year: object) -> int:
    """``year`` when it is an int inside the valid range, else a ``ValueError``."""
    if not isinstance(year, int) or year < MIN_SEASON or year > MAX_SEASON:
        raise ValueError(f"season {year} outside valid range {MIN_SEASON}..{MAX_SEASON}")
    return year


def _expand(part: str) -> range:
    """The years of one entry: a single year (``2023``) or an inclusive range (``2015-2017``)."""
    if "-" not in part:
        try:
            year = int(part)
        except ValueError:
            raise ValueError(f"non-numeric season {part!r}") from None
        return range(_check_range(year), year + 1)
    pieces = [piece.strip() for piece in part.split("-")]
    if len(pieces) != 2 or not all(pieces):
        raise ValueError(f"invalid season range {part!r}")
    try:
        start, end = int(pieces[0]), int(pieces[1])
    except ValueError:
        raise ValueError(f"non-numeric season in range {part!r}") from None
    if start > end:
        raise ValueError(f"reversed season range {start}-{end}; expected start <= end")
    return range(_check_range(start), _check_range(end) + 1)


__all__ = ["parse_seasons"]
