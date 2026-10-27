"""Strict coercion helpers: parse or raise ``CoercionError`` — never silently return NULL."""

from datetime import date, datetime
from typing import Any

NULL_TOKENS = frozenset({"", "NA", "N/A", "null", "None", "(null)", "<NA>", "NaN", "nan", "--"})


class CoercionError(ValueError):
    """Raised when a non-null value cannot be coerced to the requested type."""


def _is_null(value: Any, nulls: frozenset[str]) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip() in nulls


def to_int(value: Any, *, nulls: frozenset[str] = NULL_TOKENS) -> int | None:
    """Coerce to int; null tokens give None, garbage raises ``CoercionError``."""
    if _is_null(value, nulls):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        if isinstance(value, float):
            if value != value or value in (float("inf"), float("-inf")):
                raise CoercionError(f"cannot convert non-finite float {value!r} to int")
            if value != int(value):
                raise CoercionError(f"refusing to truncate float {value!r} to int")
            return int(value)
        text = str(value).strip().replace(",", "")
        try:
            return int(text)
        except ValueError:
            number = float(text)
            if number != number or number != int(number):
                raise CoercionError(f"cannot convert {value!r} to int without loss") from None
            return int(number)
    except (ValueError, OverflowError, TypeError) as exc:
        if isinstance(exc, CoercionError):
            raise
        raise CoercionError(f"cannot convert {value!r} to int") from exc


def to_float(
    value: Any, *, nulls: frozenset[str] = NULL_TOKENS, strip_percent: bool = False
) -> float | None:
    """Coerce to float; null tokens give None, garbage raises ``CoercionError``."""
    if _is_null(value, nulls):
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().replace(",", "")
    if strip_percent:
        text = text.rstrip("%")
    try:
        return float(text)
    except ValueError as exc:
        raise CoercionError(f"cannot convert {value!r} to float") from exc


def to_bool(value: Any, *, nulls: frozenset[str] = NULL_TOKENS) -> bool | None:
    """Coerce to bool; null tokens give None, garbage raises ``CoercionError``."""
    if _is_null(value, nulls):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "t", "true", "y", "yes"):
        return True
    if text in ("0", "f", "false", "n", "no"):
        return False
    raise CoercionError(f"cannot convert {value!r} to bool")


def to_date(
    value: Any, fmt: str = "%Y-%m-%d", *, nulls: frozenset[str] = NULL_TOKENS
) -> date | None:
    """Coerce to date using ``fmt``; null tokens give None, garbage raises ``CoercionError``."""
    if _is_null(value, nulls):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), fmt).date()
    except ValueError as exc:
        raise CoercionError(f"cannot convert {value!r} to date with format {fmt!r}") from exc
