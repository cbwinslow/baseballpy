"""Header-based normalization helpers shared by flat-file sources (Lahman, Chadwick, Retrosheet).

Rules (see the ``complete-source-coverage`` design): nothing is dropped, types never come from
column-name guessing, unknown columns are preserved in a trailing ``_extras`` JSON string column and
logged once, and uncastable cells are quarantined (never silently NULLed).
"""

import csv
import io
import json
import logging
import re
import threading
from collections.abc import Iterable, Sequence

import pyarrow as pa
import pyarrow.csv as pacsv

from baseballpy.core.quarantine import Quarantine, checked_cast

logger = logging.getLogger(__name__)

EXTRAS = "_extras"
NULL_TOKENS = ("",)  # sources use empty cells for NULL; "NA" is real data (lgID NA, Namibia)
BOM = "﻿"

_CAMEL_1 = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_2 = re.compile(r"([a-z0-9])([A-Z])")
_NON_WORD = re.compile(r"[^0-9a-zA-Z]+")

_TYPES: dict[str, pa.DataType] = {
    "string": pa.string(),
    "bool": pa.bool_(),
    "int8": pa.int8(),
    "int16": pa.int16(),
    "int32": pa.int32(),
    "int64": pa.int64(),
    "float32": pa.float32(),
    "float64": pa.float64(),
    "date32": pa.date32(),
}

_warned: set[tuple[str, str, str]] = set()
_warned_lock = threading.Lock()


def snake(name: str) -> str:
    """``camelCase``/``PascalCase``/``kebab-case`` header -> ``snake_case`` (deterministic)."""
    text = _NON_WORD.sub("_", name.strip().lstrip(BOM))
    text = _CAMEL_2.sub(r"\1_\2", _CAMEL_1.sub(r"\1_\2", text))
    return re.sub(r"_+", "_", text).strip("_").lower()


def pa_type(name: str) -> pa.DataType:
    """Arrow type for a type name used in generated schema modules."""
    try:
        return _TYPES[name]
    except KeyError:
        raise ValueError(
            f"unknown column type {name!r}; expected one of {sorted(_TYPES)}"
        ) from None


def schema_from_columns(columns: Iterable[tuple[str, str]], *, extras: bool = True) -> pa.Schema:
    """Build a schema from ``(name, type_name)`` pairs, appending ``_extras`` when requested."""
    fields = [pa.field(name, pa_type(type_name)) for name, type_name in columns]
    if extras:
        fields.append(pa.field(EXTRAS, pa.string()))
    return pa.schema(fields)


def infer_type_name(values: Iterable[str | None]) -> str:
    """Propose a type name from a full sample of string cells (conservative, never ``int8``).

    Integers narrow to ``int16`` only when every value is within +-20000 (leaving headroom),
    otherwise ``int32``/``int64``; ISO dates become ``date32``; anything else is ``string``.
    """
    seen = False
    is_int = is_float = is_date = True
    low = high = 0
    for raw in values:
        if raw is None:
            continue
        value = raw.strip()
        if value in NULL_TOKENS:
            continue
        seen = True
        if is_int:
            try:
                number = int(value)
            except ValueError:
                is_int = False
            else:
                low, high = min(low, number), max(high, number)
        if is_float and not is_int:
            try:
                float(value)
            except ValueError:
                is_float = False
        if is_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            is_date = False
        if not (is_int or is_float or is_date):
            return "string"
    if not seen:
        return "string"
    if is_int:
        span = max(abs(low), abs(high))
        if span <= 20000:
            return "int16"
        return "int32" if span <= 2_000_000_000 else "int64"
    if is_float:
        return "float64"
    return "date32" if is_date else "string"


def _clean_header(name: str) -> str:
    return name.lstrip(BOM).strip()


def read_csv_strings(raw: bytes | str, *, delimiter: str = ",") -> pa.Table:
    """Read a header-bearing CSV with every column as a nullable string (BOM-safe)."""
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    if not data.strip():
        return pa.table({})
    first_line = data.split(b"\n", 1)[0].decode("utf-8-sig", errors="replace").rstrip("\r")
    names = next(csv.reader([first_line], delimiter=delimiter))
    cleaned = [_clean_header(n) for n in names]
    table = pacsv.read_csv(
        io.BytesIO(data),
        read_options=pacsv.ReadOptions(column_names=cleaned, skip_rows=1),
        parse_options=pacsv.ParseOptions(delimiter=delimiter),
        convert_options=pacsv.ConvertOptions(
            column_types=dict.fromkeys(cleaned, pa.string()),
            strings_can_be_null=True,
            null_values=list(NULL_TOKENS),
        ),
    )
    return table


def _warn_once(source: str, dataset: str, fields: Sequence[str]) -> list[str]:
    fresh: list[str] = []
    with _warned_lock:
        for name in fields:
            key = (source, dataset, name)
            if key not in _warned:
                _warned.add(key)
                fresh.append(name)
    if fresh:
        logger.warning(
            "schema_drift: %s/%s has unknown column(s) %s; preserving them in %s",
            source,
            dataset,
            fresh,
            EXTRAS,
        )
    return fresh


def reset_drift_warnings() -> None:
    """Forget which drifted columns were already logged (tests)."""
    with _warned_lock:
        _warned.clear()


def normalize_csv(
    raw: bytes | str,
    schema: pa.Schema,
    *,
    source: str,
    dataset: str,
    quarantine: Quarantine | None = None,
    delimiter: str = ",",
) -> pa.Table:
    """Map a header-bearing CSV onto ``schema``; unknown columns go to ``_extras`` as JSON.

    Columns are matched by exact header, then case-insensitively. Missing columns become NULL,
    uncastable cells are quarantined by :func:`checked_cast`, and columns absent from the schema
    are serialised per row into ``_extras`` (only when the schema declares that column).
    """
    table = read_csv_strings(raw, delimiter=delimiter)
    wants_extras = EXTRAS in schema.names
    known = [f for f in schema if f.name != EXTRAS]
    by_lower = {name.lower(): name for name in table.column_names}
    used: set[str] = set()
    columns: list[pa.ChunkedArray | pa.Array] = []
    num_rows = table.num_rows
    for field in known:
        source_name = (
            field.name if field.name in table.column_names else by_lower.get(field.name.lower())
        )
        if source_name is None or source_name in used:
            columns.append(pa.nulls(num_rows, type=field.type))
            continue
        used.add(source_name)
        column = table.column(source_name)
        if field.type == pa.string():
            columns.append(column)
        else:
            columns.append(
                checked_cast(
                    column,
                    field.type,
                    quarantine=quarantine,
                    source=source,
                    dataset=dataset,
                    column=field.name,
                )
            )
    extra_names = [n for n in table.column_names if n not in used]
    fields = list(known)
    if wants_extras:
        if extra_names:
            _warn_once(source, dataset, extra_names)
            lists = [table.column(n).to_pylist() for n in extra_names]
            payload = [
                json.dumps({n: v for n, v in zip(extra_names, row, strict=True) if v is not None})
                for row in zip(*lists, strict=True)
            ]
            columns.append(pa.array([p if p != "{}" else None for p in payload], pa.string()))
        else:
            columns.append(pa.nulls(num_rows, type=pa.string()))
        fields.append(pa.field(EXTRAS, pa.string()))
    elif extra_names:
        _warn_once(source, dataset, extra_names)
    return pa.Table.from_arrays(
        [c if isinstance(c, pa.ChunkedArray) else pa.chunked_array([c]) for c in columns],
        schema=pa.schema(fields),
    )
