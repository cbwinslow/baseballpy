"""Infer the narrowest exact column type from sampled JSON values (used by the schema generators).

Types come from the data, never from column names: the type of a key is the narrowest one that
holds every sampled value. Decimal text and, when asked, short JSON numbers become exact
``decimal(P,S)``; ISO times ``timestamp``; nested values stay JSON text (``string``).
"""

import re
from typing import Any

_TIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}(:\d{2})?)")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DECIMAL = re.compile(r"-?\d+\.\d+")
_INT = re.compile(r"-?\d+")
#: JSON numbers with more decimals than this are real floats, not prices or quantities
MAX_DECIMAL_SCALE = 8
MAX_INT64 = 2**63 - 1


def decimal_type(texts: list[str]) -> str:
    """``decimal(P,S)`` wide enough for every text, with headroom for larger values later."""
    scale = max(len(t.partition(".")[2]) for t in texts)
    digits = max(len(t.lstrip("-").partition(".")[0]) for t in texts)
    precision = (
        9 if digits + scale <= 5 else 18 if digits + scale <= 14 else 38
    )  # headroom: a busy hour holds far more contracts than a quiet sample
    return f"decimal({precision},{scale})"


def infer(values: list[Any], *, floats_as_decimal: bool = False) -> str:
    """The type name for every sampled value of one key (``string`` when nothing fits).

    ``floats_as_decimal``: JSON numbers that are written with at most 8 decimals become exact
    decimals (Polymarket sends prices as JSON numbers such as ``0.9965``).
    """
    seen = [v for v in values if v is not None and v != ""]
    if not seen:
        return "string"
    if all(isinstance(v, bool) for v in seen):
        return "bool"
    if any(isinstance(v, bool) for v in seen):
        return "string"
    if all(isinstance(v, int) for v in seen):
        span = max(abs(v) for v in seen)
        if span > MAX_INT64:
            return "string"  # a number that does not fit 64 bits is an identifier, not a count
        return (
            "int32" if span <= 2_000_000_000 else "int64"
        )  # no int16: a later value may be larger
    if all(isinstance(v, int | float) for v in seen):
        if floats_as_decimal:
            texts = [repr(v) for v in seen]
            if all(
                "e" not in t.lower() and len(t.partition(".")[2]) <= MAX_DECIMAL_SCALE
                for t in texts
            ):
                return decimal_type([t if "." in t else t + ".0" for t in texts])
        return "float64"
    if all(isinstance(v, str) for v in seen):
        texts = [str(v) for v in seen]
        if all(_TIME.fullmatch(t) for t in texts):
            return "timestamp"
        if all(_DATE.fullmatch(t) for t in texts):
            return "date32"
        if all(_DECIMAL.fullmatch(t) or _INT.fullmatch(t) for t in texts) and any(
            _DECIMAL.fullmatch(t) for t in texts
        ):
            return decimal_type(texts)
        if all(_INT.fullmatch(t) for t in texts):
            span = max(abs(int(t)) for t in texts)
            if span <= MAX_INT64 and not any(
                len(t.lstrip("-")) > 1 and t.lstrip("-").startswith("0") for t in texts
            ):
                return "int32" if span <= 2_000_000_000 else "int64"
    return "string"


__all__ = ["MAX_DECIMAL_SCALE", "decimal_type", "infer"]
