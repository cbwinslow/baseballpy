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
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from baseballpy.core.quarantine import Quarantine, checked_cast, get_quarantine

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


def split_type_name(name: str) -> tuple[str, str | None]:
    """``"date32:%m/%d/%Y"`` -> ``("date32", "%m/%d/%Y")``; plain names have no format."""
    base, _, fmt = name.partition(":")
    return base, (fmt or None)


def pa_type(name: str) -> pa.DataType:
    """Arrow type for a type name used in generated schema modules (formats are ignored)."""
    base, _ = split_type_name(name)
    try:
        return _TYPES[base]
    except KeyError:
        raise ValueError(
            f"unknown column type {name!r}; expected one of {sorted(_TYPES)}"
        ) from None


#: field-metadata keys: upstream header(s) a column is read from (``|``-separated aliases) and the
#: ``strptime`` format used to parse a ``date32`` column from text
UPSTREAM_KEY = b"upstream"
FORMAT_KEY = b"format"

ColumnDef = tuple[str, str] | tuple[str, str, str]


def schema_from_columns(columns: Iterable[ColumnDef], *, extras: bool = True) -> pa.Schema:
    """Build a schema from ``(name, type_name[, upstream_header])`` tuples.

    ``type_name`` may carry a date format (``date32:%Y%m%d``); a differing ``upstream_header``
    (aliases separated by ``|``) is kept in field metadata so mapping stays header-based while the
    column gets a clean name. ``_extras`` is appended when requested.
    """
    fields = []
    for column in columns:
        name, type_name = column[0], column[1]
        upstream = column[2] if len(column) > 2 else name
        _, fmt = split_type_name(type_name)
        meta: dict[bytes, bytes] = {}
        if upstream != name:
            meta[UPSTREAM_KEY] = upstream.encode("utf-8")
        if fmt:
            meta[FORMAT_KEY] = fmt.encode("utf-8")
        fields.append(pa.field(name, pa_type(type_name), metadata=meta or None))
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


def dedupe_headers(names: Sequence[str]) -> list[str]:
    """Unique, non-empty header names: ``''`` -> ``col_<n>``; repeats get ``__2``, ``__3``..."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for index, raw in enumerate(names):
        name = _clean_header(raw) or f"col_{index + 1}"
        seen[name] = seen.get(name, 0) + 1
        out.append(name if seen[name] == 1 else f"{name}__{seen[name]}")
    return out


def read_csv_strings(
    raw: bytes | str, *, delimiter: str = ",", header: Sequence[str] | None = None
) -> pa.Table:
    """Read a CSV with every column as a nullable string (BOM-safe, duplicate-header-safe).

    ``header`` supplies the column names for files that have no header row (the first row is then
    data); otherwise the first row is the header.
    """
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    if not data.strip():
        return pa.table({})
    if header is None:
        first_line = data.split(b"\n", 1)[0].decode("utf-8-sig", errors="replace").rstrip("\r")
        names = next(csv.reader([first_line], delimiter=delimiter))
        skip = 1
    else:
        names, skip = list(header), 0
    cleaned = dedupe_headers(names)
    try:
        return pacsv.read_csv(
            io.BytesIO(data),
            read_options=pacsv.ReadOptions(column_names=cleaned, skip_rows=skip),
            parse_options=pacsv.ParseOptions(delimiter=delimiter),
            convert_options=pacsv.ConvertOptions(
                column_types=dict.fromkeys(cleaned, pa.string()),
                strings_can_be_null=True,
                null_values=list(NULL_TOKENS),
            ),
        )
    except pa.ArrowInvalid:
        return _read_ragged(data, cleaned, skip, delimiter)


def _read_ragged(data: bytes, names: list[str], skip: int, delimiter: str) -> pa.Table:
    """Slow path for files with rows of unexpected width (seen in Retrosheet discrepancy files).

    Short rows are padded with NULLs; rows *longer* than the header keep their surplus cells in
    extra ``col_<n>`` columns, so no cell is ever dropped. The number of ragged rows is logged.
    """
    text = data.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))[skip:]
    width = max([len(names), *(len(r) for r in rows)]) if rows else len(names)
    all_names = [*names, *(f"col_{i + 1}" for i in range(len(names), width))]
    short = sum(1 for r in rows if len(r) < len(names))
    surplus = sum(1 for r in rows if len(r) > len(names))
    if surplus:
        logger.warning(
            "%d CSV row(s) are wider than the %d-column header; surplus cells kept in extra columns",
            surplus,
            len(names),
        )
    if short:
        logger.info("%d CSV row(s) are shorter than the header; padded with NULLs", short)
    columns = [
        pa.array([(r[i] if i < len(r) and r[i] != "" else None) for r in rows], pa.string())
        for i in range(width)
    ]
    return pa.Table.from_arrays(columns, names=all_names)


def parse_dates(
    column: pa.ChunkedArray,
    fmt: str,
    *,
    source: str,
    dataset: str,
    name: str,
    quarantine: Quarantine | None = None,
) -> pa.ChunkedArray:
    """Parse text dates with ``fmt``; values that do not parse become NULL and are quarantined."""
    parsed = pc.strptime(column, format=fmt, unit="s", error_is_null=True)
    result = parsed.cast(pa.date32())
    lost = pc.and_(pc.is_valid(column), pc.is_null(result))
    if pc.any(lost).as_py():
        values = column.filter(lost).to_pylist()
        (quarantine or get_quarantine()).write(
            source,
            dataset,
            [{"column": name, "value": v} for v in values],
            f"dates in column {name!r} not matching {fmt}",
        )
    return result


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


def _find_source(field: pa.Field, table: pa.Table, by_lower: dict[str, str]) -> str | None:
    """The table column a schema field reads from (upstream aliases, then its own name)."""
    meta = field.metadata or {}
    upstream: bytes = meta.get(UPSTREAM_KEY, b"")
    candidates: list[str] = [c for c in upstream.decode("utf-8").split("|") if c]
    candidates.append(field.name)
    for candidate in candidates:
        if candidate in table.column_names:
            return candidate
    for candidate in candidates:
        if (hit := by_lower.get(candidate.lower())) is not None:
            return hit
    return None


def normalize_csv(
    raw: bytes | str,
    schema: pa.Schema,
    *,
    source: str,
    dataset: str,
    quarantine: Quarantine | None = None,
    delimiter: str = ",",
    header: Sequence[str] | None = None,
) -> pa.Table:
    """Map a CSV onto ``schema`` by header name; unknown columns go to ``_extras`` as JSON.

    Columns are matched through the field's ``upstream`` alias(es), then its own name, exact then
    case-insensitively. Missing columns become NULL, uncastable cells (and dates that do not match
    the column's declared format) are quarantined, and columns absent from the schema are
    serialised per row into ``_extras`` (only when the schema declares that column).
    """
    table = read_csv_strings(raw, delimiter=delimiter, header=header)
    wants_extras = EXTRAS in schema.names
    known = [f for f in schema if f.name != EXTRAS]
    by_lower = {name.lower(): name for name in table.column_names}
    used: set[str] = set()
    columns: list[pa.ChunkedArray | pa.Array] = []
    num_rows = table.num_rows
    for field in known:
        source_name = _find_source(field, table, by_lower)
        if source_name is None or source_name in used:
            columns.append(pa.nulls(num_rows, type=field.type))
            continue
        used.add(source_name)
        column = table.column(source_name)
        fmt = (field.metadata or {}).get(FORMAT_KEY)
        if field.type == pa.string():
            columns.append(column)
        elif fmt is not None and pa.types.is_date32(field.type):
            columns.append(
                parse_dates(
                    column,
                    fmt.decode("utf-8"),
                    source=source,
                    dataset=dataset,
                    name=field.name,
                    quarantine=quarantine,
                )
            )
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
    fields = [pa.field(f.name, f.type) for f in known]
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
