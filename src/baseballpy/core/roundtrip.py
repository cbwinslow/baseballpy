"""The round-trip check: is every cell of the provider's text still there, unchanged, in our processed table?

For one dataset it reads raw CSV files (plain or gzipped, header row), keeps each cell as text and compares every
cell with the stored value:

* when the registered key columns identify each processed row once, each sampled raw row is found by its key;
* when they do not (a key that repeats, as in Lahman's award tables), all raw files of the season are compared with
  the processed rows column by column as multisets of values;
* text exactly; an integer by its text (so ``01405134`` stored as ``1405134`` is caught); a float by value as a
  64-bit float (so ``85.8`` stored as a 32-bit float is caught); a date by its declared format;
* a non-empty raw cell stored as NULL is ``lost_to_null`` (the quarantine rows of the dataset are reported beside it);
* a raw row with no processed row is ``row_missing``;
* a raw column that no schema column reads is ``unmapped_raw_column`` unless ``_extras`` holds it.

It is offline and read-only. A source whose raw files are not CSV (JSON answers, event files, zip members) is
``skipped`` with the reason, never reported as clean. :func:`register_raw_reader` lets a source supply its own raw
tables (Retrosheet's zip members, Statcast's embedded-JSON pages).
"""

import gzip
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import LINEAGE_COLUMN, DatasetSpec
from baseballpy.core.schema_tools import EXTRAS, FORMAT_KEY, UPSTREAM_KEY, read_csv_strings

CHANGED_CELL = "changed_cell"
LOST_TO_NULL = "lost_to_null"
ROW_MISSING = "row_missing"
ROW_EXTRA = "row_extra"
UNMAPPED_RAW_COLUMN = "unmapped_raw_column"
_LEADING_ZERO = re.compile(r"^[+-]?0\d")
_SKIP = (EXTRAS, LINEAGE_COLUMN)
Column: TypeAlias = pa.ChunkedArray | pa.Array


@dataclass(frozen=True)
class Loss:
    """One kind of difference in one column, with how many cells and one example."""

    kind: str
    column: str
    count: int
    example: str


@dataclass
class DatasetCheck:
    """The verdict for one dataset."""

    source: str
    dataset: str
    status: str = "ok"
    reason: str = ""
    raw_rows: int = 0
    compared: int = 0
    files: list[str] = field(default_factory=list)
    losses: list[Loss] = field(default_factory=list)
    quarantined: int = 0
    #: what the check could not decide (for example several fetched versions of the same row)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RawSample:
    """One raw file turned into a table of text cells; ``season`` picks the processed folder."""

    label: str
    season: int | None
    table: pa.Table
    #: the file name without its suffix (a roster's team and year are in it)
    stem: str = ""


@dataclass
class _Entry:
    count: int = 0
    example: str = ""


_Losses = dict[tuple[str, str], _Entry]


def _add(losses: _Losses, kind: str, column: str, count: int, example: str) -> None:
    entry = losses.setdefault((kind, column), _Entry())
    entry.count += count
    entry.example = entry.example or example


#: ``reader(config, spec, sample_files, season)``: the sampled raw files (``season=None``: spread over the seasons),
#: or every raw file of one season
RawReader = Callable[[LakeConfig, DatasetSpec, int, int | None, bool], Iterable[RawSample]]
_READERS: dict[str, RawReader] = {}
#: ``(source, dataset)`` -> ``counter(config, season)``: rows the season must hold, counted from raw files that are not CSV
CountCheck = Callable[[LakeConfig, int], int]
_COUNTS: dict[tuple[str, str], CountCheck] = {}


def register_count_check(source: str, dataset: str, counter: CountCheck) -> None:
    """Register how many rows a season of ``dataset`` must have, for raw files the cell check cannot read."""
    _COUNTS[(source, dataset)] = counter


def register_raw_reader(source: str, reader: RawReader) -> None:
    """Register how the raw files of a source's datasets become tables of text (default: CSV files)."""
    _READERS[source] = reader


def _files(folder: Path, suffixes: Sequence[str]) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and not p.name.startswith("_") and p.name.endswith(tuple(suffixes))
    )


def _spread(items: list[Path], count: int) -> list[Path]:
    """``count`` files spread evenly over the sorted list (first, middle, last, ...)."""
    if count >= len(items):
        return items
    if count <= 1:
        return items[:1]
    return [items[round(i * (len(items) - 1) / (count - 1))] for i in range(count)]


def _season_dirs(config: LakeConfig, spec: DatasetSpec) -> list[tuple[int | None, Path]]:
    base = config.raw_dir(spec.source, spec.name)
    if spec.partition != "season":
        return [(None, base)]
    if not base.is_dir():
        return []
    out: list[tuple[int | None, Path]] = []
    for child in sorted(base.iterdir()):
        if child.is_dir() and child.name.startswith("season=") and child.name[7:].isdigit():
            out.append((int(child.name[7:]), child))
    return out


def csv_samples(
    config: LakeConfig,
    spec: DatasetSpec,
    sample_files: int,
    season: int | None = None,
    every: bool = False,
    *,
    suffixes: Sequence[str] = (".csv", ".csv.gz"),
    decode: Callable[[bytes], bytes] | None = None,
    header: Sequence[str] | None = None,
) -> list[RawSample]:
    """Raw files of the dataset as text tables: spread over the seasons, or every file of ``season``.

    ``decode`` turns the bytes of a file (after gunzip) into CSV bytes (a page with an embedded JSON array).
    """
    candidates: list[tuple[int | None, Path]] = []
    for folder_season, folder in _season_dirs(config, spec):
        if season is None or folder_season == season:
            candidates += [(folder_season, p) for p in _files(folder, suffixes)]
    paths = [p for _, p in candidates]
    chosen = paths if every else _spread(paths, sample_files)
    by_path = {p: s for s, p in candidates}
    out: list[RawSample] = []
    for path in chosen:
        data = path.read_bytes()
        if path.name.endswith(".gz"):
            data = gzip.decompress(data)
        if decode is not None:
            data = decode(data)
        out.append(
            RawSample(path.name, by_path[path], read_csv_strings(data, header=header), path.stem)
        )
    return out


def _quarantine_rows(config: LakeConfig, spec: DatasetSpec) -> int:
    base = config.quarantine_root / spec.source
    if not base.is_dir():
        return 0
    total = 0
    for path in base.rglob(f"{spec.name}-*.jsonl"):
        text = path.read_text(encoding="utf-8", errors="replace")
        total += sum(1 for line in text.splitlines() if line.strip())
    return total


def _processed_table(
    config: LakeConfig, spec: DatasetSpec, season: int | None
) -> tuple[pa.Table, int] | None:
    folder = config.processed_dir(spec.source, spec.name, season)
    files = (
        sorted(p for p in folder.glob("*.parquet") if not p.name.startswith("_"))
        if folder.is_dir()
        else []
    )
    if not files:
        return None
    tables = [pq.read_table(p) for p in files]
    return pa.concat_tables(tables, promote_options="default"), len(files)


def _aliases(field_: pa.Field) -> list[str]:
    meta = field_.metadata or {}
    return str((meta.get(UPSTREAM_KEY) or field_.name.encode()).decode()).split("|")


def _raw_column(names: list[str], raw: pa.Table) -> str | None:
    lower = {c.lower(): c for c in raw.column_names}
    for name in names:
        if name in raw.column_names:
            return name
    for name in names:
        if name.lower() in lower:
            return str(lower[name.lower()])
    return None


def _columns(spec: DatasetSpec, raw: pa.Table) -> dict[str, str]:
    return {
        f.name: found
        for f in spec.schema
        if f.name not in _SKIP and (found := _raw_column(_aliases(f), raw)) is not None
    }


def _text(column: Column) -> Column:
    return pc.cast(column, pa.string()) if not pa.types.is_string(column.type) else column


def _date_format(field_: pa.Field, raw_col: Column) -> str:
    """The text format of a date column: the schema's declared one, else read from the raw cells."""
    declared = (field_.metadata or {}).get(FORMAT_KEY)
    if declared:
        return str(declared.decode("utf-8"))
    cells = [str(v).strip() for v in pc.drop_null(raw_col).slice(0, 50).to_pylist() if v]
    if cells and all(re.fullmatch(r"\d{8}", v) for v in cells):
        return "%Y%m%d"
    if cells and all(re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", v) for v in cells):
        return "%m/%d/%Y"
    return "%Y-%m-%d"


def _key_text(
    raw: pa.Table, processed: pa.Table, spec: DatasetSpec, columns: dict[str, str]
) -> tuple[Column, Column] | None:
    """Key text of every raw row and of every processed row, or ``None`` when a key column cannot be compared."""
    raw_parts: list[Column] = []
    out_parts: list[Column] = []
    for key in spec.keys:
        if key not in spec.schema.names or key not in columns or key not in processed.column_names:
            return None
        field_ = spec.schema.field(key)
        type_ = field_.type
        if pa.types.is_date32(type_):
            fmt = _date_format(field_, raw.column(columns[key]))
            # the processed date is written back in the raw format and compared as text
            raw_parts.append(pc.utf8_trim_whitespace(raw.column(columns[key])))
            out_parts.append(pc.strftime(processed.column(key), format=fmt))
            continue
        if not (
            pa.types.is_string(type_) or pa.types.is_integer(type_) or pa.types.is_dictionary(type_)
        ):
            return None
        raw_parts.append(pc.utf8_trim_whitespace(raw.column(columns[key])))
        out_parts.append(_text(processed.column(key)))
    if not raw_parts:
        return None
    raw_key, out_key = raw_parts[0], out_parts[0]
    for a, b in zip(raw_parts[1:], out_parts[1:], strict=True):
        raw_key = pc.binary_join_element_wise(
            raw_key, a, "|", null_handling="replace", null_replacement=""
        )
        out_key = pc.binary_join_element_wise(
            out_key, b, "|", null_handling="replace", null_replacement=""
        )
    return raw_key, out_key


def _sum(mask: Column) -> int:
    total: int = pc.sum(pc.cast(mask, pa.int64())).as_py() or 0
    return total


def _first(raw: Column, out: Column, mask: Column) -> str:
    rows = pc.filter(pa.table({"r": raw, "o": out}), mask).slice(0, 1).to_pylist()
    return f"raw {rows[0]['r']!r} became {rows[0]['o']!r}" if rows else ""


_FLOAT_TEXT = r"^\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?\s*$"


def _parse_float(raw: Column) -> Column:
    """Raw text as 64-bit floats; a cell that is not a number becomes NULL (it was quarantined or is text)."""
    text = pc.utf8_trim_whitespace(raw)
    parseable = pc.fill_null(pc.match_substring_regex(text, _FLOAT_TEXT), False)
    return pc.cast(pc.if_else(parseable, text, pa.scalar(None, pa.string())), pa.float64())


def _float_mismatch(raw: Column, out: Column, both: Column) -> Column:
    parsed = _parse_float(raw)
    stored = pc.cast(out, pa.float64())
    differ = pc.and_(
        pc.not_equal(parsed, stored), pc.invert(pc.fill_null(pc.is_nan(parsed), False))
    )
    return pc.and_(both, pc.fill_null(differ, False))


def _same_number(item: str, value: object) -> bool:
    """``1.0`` for 1 is the same number; ``+5`` and ``007`` are not what the provider wrote."""
    try:
        return float(item) == float(str(value)) and not _LEADING_ZERO.match(item)
    except ValueError:
        return False


def _int_mismatch(raw: Column, out: Column, both: Column) -> Column:
    """Integers by their text; only the cells whose text differs are looked at one by one."""
    trimmed = pc.utf8_trim_whitespace(raw)
    differ = pc.fill_null(pc.not_equal(trimmed, pc.cast(out, pa.string())), False)
    first_pass = pc.and_(both, differ)
    if not _sum(first_pass):
        return first_pass
    positions = pc.indices_nonzero(first_pass)
    items = pc.take(trimmed, positions).to_pylist()
    values = pc.take(out, positions).to_pylist()
    really = [
        int(pos)
        for pos, item, value in zip(positions.to_pylist(), items, values, strict=True)
        if not _same_number(str(item), value)
    ]
    if not really:
        return pc.and_(first_pass, pa.scalar(False))
    return pc.is_in(pa.array(range(len(raw)), pa.int64()), value_set=pa.array(really, pa.int64()))


def _date_mismatch(raw: Column, out: Column, both: Column, fmt: str) -> Column:
    """A date by the text it would have in the raw format (compared as text, in Arrow)."""
    written = pc.strftime(out, format=fmt)
    differ = pc.fill_null(pc.not_equal(pc.utf8_trim_whitespace(raw), written), False)
    return pc.and_(both, differ)


_TRUE = ["true", "t", "1", "y", "yes"]
_FALSE = ["false", "f", "0", "n", "no"]


def _bool_text(raw: Column) -> Column:
    """Raw text as the words ``true`` / ``false`` (anything else stays as written, so it shows as a difference)."""
    low = pc.utf8_lower(pc.utf8_trim_whitespace(raw))
    return pc.if_else(
        pc.is_in(low, value_set=pa.array(_TRUE)),
        "true",
        pc.if_else(pc.is_in(low, value_set=pa.array(_FALSE)), "false", low),
    )


def _bool_mismatch(raw: Column, out: Column, both: Column) -> Column:
    differ = pc.fill_null(pc.not_equal(_bool_text(raw), pc.cast(out, pa.string())), False)
    return pc.and_(both, differ)


def _compare_aligned(
    spec: DatasetSpec,
    raw: pa.Table,
    out: pa.Table,
    columns: dict[str, str],
    losses: _Losses,
    not_compared: set[str],
    notes: list[str],
) -> None:
    """Compare every mapped column of two tables with the same length and row order.

    Text is compared after trimming the spaces round the raw cell (the parsers trim them: ``' Paul'`` is stored as
    ``'Paul'``); how many cells that touched is a note, not a loss.
    """
    for field_ in spec.schema:
        if field_.name in _SKIP or field_.name not in columns:
            continue
        raw_col = raw.column(columns[field_.name])
        out_col = out.column(field_.name)
        raw_null = pc.is_null(raw_col)
        out_null = pc.is_null(out_col)
        lost = pc.and_(pc.invert(raw_null), out_null)
        invented = pc.and_(raw_null, pc.invert(out_null))
        both = pc.and_(pc.invert(raw_null), pc.invert(out_null))
        type_ = field_.type
        if pa.types.is_dictionary(type_):
            out_col = pc.cast(out_col, pa.string())
            type_ = pa.string()
        if pa.types.is_string(type_) or pa.types.is_large_string(type_):
            out_text = pc.cast(out_col, pa.string())
            bad = pc.and_(both, pc.fill_null(pc.not_equal(raw_col, out_text), False))
            trimmed_raw = pc.utf8_trim_whitespace(raw_col)
            spaces_only = pc.and_(bad, pc.fill_null(pc.equal(trimmed_raw, out_text), False))
            if _sum(spaces_only):
                notes.append(
                    f"{field_.name}: {_sum(spaces_only):,} cell(s) had spaces round the text, stored trimmed"
                )
                bad = pc.and_(bad, pc.invert(spaces_only))
        elif pa.types.is_integer(type_):
            bad = _int_mismatch(raw_col, out_col, both)
        elif pa.types.is_floating(type_):
            bad = _float_mismatch(raw_col, out_col, both)
        elif pa.types.is_date32(type_):
            fmt = _date_format(field_, raw_col)
            bad = _date_mismatch(raw_col, out_col, both, fmt)
        elif pa.types.is_boolean(type_):
            bad = _bool_mismatch(raw_col, out_col, both)
        else:
            not_compared.add(f"{field_.name} ({type_})")
            continue
        for kind, mask in ((LOST_TO_NULL, lost), (CHANGED_CELL, pc.or_(bad, invented))):
            n = _sum(mask)
            if n:
                _add(losses, kind, field_.name, n, _first(raw_col, out_col, mask))


def _canonical_pair(field_: pa.Field, raw: Column, out: Column) -> tuple[Column, Column] | None:
    """The raw column and the processed column in one comparable form, or ``None`` for a type not compared.

    Text and dictionary columns as text; integers by their text; floats as 64-bit floats; dates as text in the
    raw format. Everything stays in Arrow, so memory follows the data, not Python objects.
    """
    type_ = field_.type
    if pa.types.is_dictionary(type_):
        return raw, pc.cast(out, pa.string())
    if pa.types.is_string(type_) or pa.types.is_large_string(type_):
        return pc.utf8_trim_whitespace(raw), pc.cast(out, pa.string())  # parsers trim cells
    if pa.types.is_integer(type_):
        return pc.utf8_trim_whitespace(raw), pc.cast(out, pa.string())
    if pa.types.is_floating(type_):
        return _parse_float(raw), pc.cast(out, pa.float64())
    if pa.types.is_date32(type_):
        return pc.utf8_trim_whitespace(raw), pc.strftime(out, format=_date_format(field_, raw))
    if pa.types.is_boolean(type_):
        return _bool_text(raw), pc.cast(out, pa.string())
    return None


def _counts(values: Column, name: str) -> pa.Table:
    """Each distinct non-null value of ``values`` with how many times it occurs."""
    counted = pc.value_counts(values)
    table = pa.table({"v": counted.field("values"), name: counted.field("counts")})
    return table.filter(pc.is_valid(table.column("v")))


def _multiset_difference(raw: Column, out: Column) -> tuple[int, str, str]:
    """How many raw values occur more often in the raw text than in the processed rows, with one example each side."""
    left, right = _counts(raw, "rc"), _counts(out, "oc")
    joined = left.join(right, keys="v", join_type="left outer")
    deficit = pc.subtract(joined.column("rc"), pc.fill_null(joined.column("oc"), 0))
    short = pc.greater(deficit, 0)
    count = _sum(pc.multiply(pc.cast(short, pa.int64()), deficit))
    if not count:
        return 0, "", ""
    raw_example = pc.filter(joined.column("v"), short).slice(0, 1).to_pylist()
    extra = right.join(left, keys="v", join_type="left anti")
    out_example = extra.column("v").slice(0, 1).to_pylist()
    return count, repr(raw_example[0]), repr(out_example[0]) if out_example else "(no value)"


def _compare_multisets(
    spec: DatasetSpec,
    raws: list[pa.Table],
    out: pa.Table,
    losses: _Losses,
    notes: list[str],
    not_compared: set[str],
) -> int:
    """For keys that repeat: per column, the values of all raw rows against all processed rows, as multisets.

    Returns the number of raw rows. A value present more often in the raw text than in the processed rows is a
    change (or a NULL, when the processed rows hold more NULLs than the raw text); the example names one value of
    each side. All counting is done in Arrow on distinct values, never on Python lists of rows.
    """
    raw = pa.concat_tables(raws, promote_options="default")
    seen = int(raw.num_rows)
    columns = _columns(spec, raw)
    if raw.num_rows > out.num_rows:
        # more raw rows than processed rows: exact duplicates from overlapping windows are dropped first; what is
        # still more means the raw files hold several fetched versions of some rows (a provider that revises data).
        # Values cannot then be compared one to one, so the check is that every key of the raw text is present.
        raw = raw.group_by(raw.column_names, use_threads=False).aggregate([])
        if raw.num_rows > out.num_rows:
            keyed = _key_text(raw, out, spec, columns)
            if keyed is None:
                extra = raw.num_rows - out.num_rows
                _add(
                    losses,
                    ROW_MISSING,
                    "",
                    extra,
                    f"{raw.num_rows} raw rows, {out.num_rows} processed",
                )
            else:
                raw_key, out_key = keyed
                missing = _sum(pc.is_null(pc.index_in(raw_key, value_set=out_key)))
                if missing:
                    _add(
                        losses,
                        ROW_MISSING,
                        "",
                        missing,
                        "a key of the raw text is not in the processed data",
                    )
                notes.append(
                    f"{raw.num_rows - out.num_rows:,} raw rows are other versions of the same keys: "
                    "keys checked, values not compared"
                )
            return seen
    if out.num_rows > raw.num_rows:  # the other direction: processed rows that no raw row explains
        _add(
            losses,
            ROW_EXTRA,
            "",
            out.num_rows - raw.num_rows,
            f"{out.num_rows} processed rows, {raw.num_rows} raw",
        )
    for field_ in spec.schema:
        if field_.name in _SKIP or field_.name not in columns:
            continue
        pair = _canonical_pair(field_, raw.column(columns[field_.name]), out.column(field_.name))
        if pair is None:
            not_compared.add(f"{field_.name} ({field_.type})")
            continue
        raw_values, out_values = pair
        raw_nulls = int(pc.sum(pc.cast(pc.is_null(raw_values), pa.int64())).as_py() or 0)
        out_nulls = int(pc.sum(pc.cast(pc.is_null(out_values), pa.int64())).as_py() or 0)
        changed, raw_example, out_example = _multiset_difference(raw_values, out_values)
        nulls = min(changed, max(0, out_nulls - raw_nulls))
        if nulls:
            _add(losses, LOST_TO_NULL, field_.name, nulls, "a non-empty raw cell is NULL")
            changed -= nulls
        if changed:
            _add(
                losses,
                CHANGED_CELL,
                field_.name,
                changed,
                f"raw {raw_example} became {out_example}",
            )
    return seen


def _check_unmapped(raw: pa.Table, out: pa.Table, columns: dict[str, str], losses: _Losses) -> None:
    used = set(columns.values())
    has_extras = EXTRAS in out.column_names
    for name in raw.column_names:
        if name in used:
            continue
        filled = pc.and_(pc.is_valid(raw.column(name)), pc.not_equal(raw.column(name), ""))
        n = _sum(filled)
        if has_extras and n:
            named = pc.fill_null(pc.match_substring(out.column(EXTRAS), f'"{name}"'), False)
            n = _sum(pc.and_(filled, pc.invert(named)))
        if n:  # an all-empty column holds nothing to lose
            _add(losses, UNMAPPED_RAW_COLUMN, name, n, "no schema column and no _extras value")


def _unique(out_key: Column, rows: int) -> bool:
    return int(pc.count_distinct(out_key).as_py() or 0) == rows


def roundtrip_dataset(
    config: LakeConfig, spec: DatasetSpec, *, sample_files: int = 3, full: bool = False
) -> DatasetCheck:
    """Compare raw files of ``spec`` with its processed rows (see the module docstring).

    By default ``sample_files`` raw files spread over the seasons are compared; with ``full`` every raw file is read
    and the check also goes the other way: a processed row that no raw row explains is ``row_extra``.
    """
    check = DatasetCheck(spec.source, spec.name)
    reader = _READERS.get(spec.source)

    def read(season: int | None, every: bool = False) -> list[RawSample]:
        if reader is not None:
            return list(reader(config, spec, sample_files, season, every))
        return csv_samples(config, spec, sample_files, season, every)

    samples = read(None, full)
    if not samples and (spec.source, spec.name) in _COUNTS:
        return _count_check(config, spec, check)
    if not samples:
        folder = config.raw_dir(spec.source, spec.name)
        has_raw = folder.is_dir() and any(folder.rglob("*"))
        check.status = "skipped"
        check.reason = (
            "the raw files are not CSV (json, text or zip): this source needs its own raw reader"
            if has_raw
            else "no raw files held for this dataset"
        )
        return check
    check.quarantined = _quarantine_rows(config, spec)
    losses: _Losses = {}
    not_compared: set[str] = set()
    for season in dict.fromkeys(s.season for s in samples):
        held = _processed_table(config, spec, season)
        if held is None:
            check.status = "skipped"
            check.reason = "no processed rows held for the season of the raw file"
            return check
        processed, part_count = held
        mine = [s for s in samples if s.season == season]
        probe = _key_text(mine[0].table, processed, spec, _columns(spec, mine[0].table))
        if probe is not None and not _unique(probe[1], processed.num_rows):
            everything = (
                mine if full else read(season, True)
            )  # the key repeats: every raw row, as multisets
            check.files += [s.label for s in everything]
            check.raw_rows += _compare_multisets(
                spec, [s.table for s in everything], processed, losses, check.notes, not_compared
            )
            check.compared += processed.num_rows
            continue
        raw_keys: list[Column] = []
        for sample in mine:
            raw = sample.table
            columns = _columns(spec, raw)
            check.files.append(sample.label)
            check.raw_rows += raw.num_rows
            keyed = _key_text(raw, processed, spec, columns)
            if keyed is not None:
                raw_key, out_key = keyed
                if full:
                    raw_keys.append(raw_key)
                index = pc.index_in(raw_key, value_set=out_key)
                missing = _sum(pc.is_null(index))
                if missing:
                    example = pc.filter(raw_key, pc.is_null(index)).slice(0, 1).to_pylist()
                    _add(
                        losses,
                        ROW_MISSING,
                        "",
                        missing,
                        f"key {example[0]!r} is not in the processed data",
                    )
                raw_used = raw.filter(pc.is_valid(index))
                out_used = processed.take(pc.drop_null(index))
            elif len(mine) == 1 and part_count == 1 and processed.num_rows == raw.num_rows:
                raw_used, out_used = raw, processed
            else:
                check.status = "skipped"
                check.reason = (
                    "no usable key column and the raw file is not one-to-one with a processed file"
                )
                return check
            check.compared += raw_used.num_rows
            _compare_aligned(spec, raw_used, out_used, columns, losses, not_compared, check.notes)
            _check_unmapped(raw_used, out_used, columns, losses)
        if full and raw_keys:  # the other direction: every processed row must come from a raw row
            keyed = _key_text(mine[0].table, processed, spec, _columns(spec, mine[0].table))
            if keyed is not None:
                every_raw = pa.chunked_array([c for k in raw_keys for c in _chunks(k)])
                orphans = pc.is_null(pc.index_in(keyed[1], value_set=every_raw))
                extra = _sum(orphans)
                if extra:
                    example = pc.filter(keyed[1], orphans).slice(0, 1).to_pylist()
                    _add(
                        losses,
                        ROW_EXTRA,
                        "",
                        extra,
                        f"key {example[0]!r} is in the processed data only",
                    )
    if not_compared:
        check.notes.append("columns not compared (type): " + ", ".join(sorted(not_compared)))
    check.losses = [
        Loss(kind, column, v.count, v.example) for (kind, column), v in sorted(losses.items())
    ]
    _explain_with_quarantine(check)
    check.status = "loss" if check.losses else "ok"
    return check


def _count_check(config: LakeConfig, spec: DatasetSpec, check: DatasetCheck) -> DatasetCheck:
    """Row counts only: each processed season against the count of its raw lines."""
    counter = _COUNTS[(spec.source, spec.name)]
    base = config.processed_dir(spec.source, spec.name)
    seasons = (
        sorted(int(p.name[7:]) for p in base.glob("season=*") if p.name[7:].isdigit())
        if base.is_dir()
        else []
    )
    for season in seasons:
        have = sum(
            pq.ParquetFile(f).metadata.num_rows
            for f in config.processed_dir(spec.source, spec.name, season).glob("*.parquet")
            if not f.name.startswith("_")
        )
        want = counter(config, season)
        check.raw_rows += want
        check.compared += min(have, want)
        check.files.append(f"season={season}")
        if want > have:
            check.losses.append(
                Loss(
                    ROW_MISSING,
                    "",
                    want - have,
                    f"season {season}: {want:,} raw lines, {have:,} rows",
                )
            )
        elif have > want:
            check.losses.append(
                Loss(
                    ROW_EXTRA,
                    "",
                    have - want,
                    f"season {season}: {want:,} raw lines, {have:,} rows",
                )
            )
    check.notes.append(
        "counts only: the raw event files are not CSV, so rows are counted, cells are not compared"
    )
    check.quarantined = _quarantine_rows(config, spec)
    check.status = "loss" if check.losses else "ok"
    return check


def _chunks(column: Column) -> list[pa.Array]:
    return list(column.chunks) if isinstance(column, pa.ChunkedArray) else [column]


def _explain_with_quarantine(check: DatasetCheck) -> None:
    """Cells turned NULL are a known verdict, not a loss, when the quarantine holds at least as many rows."""
    nulls = [x for x in check.losses if x.kind == LOST_TO_NULL]
    total = sum(x.count for x in nulls)
    if nulls and total <= check.quarantined:
        check.losses = [x for x in check.losses if x.kind != LOST_TO_NULL]
        check.notes.append(
            f"{total:,} cell(s) are NULL because they were quarantined "
            f"({check.quarantined:,} quarantine row(s)): "
            + ", ".join(sorted({x.column for x in nulls}))
        )


def roundtrip_lake(
    config: LakeConfig, specs: Iterable[DatasetSpec], *, sample_files: int = 3, full: bool = False
) -> list[DatasetCheck]:
    """:func:`roundtrip_dataset` for every spec (a dataset that cannot be read is a ``skipped`` verdict)."""
    out: list[DatasetCheck] = []
    for spec in specs:
        try:
            out.append(roundtrip_dataset(config, spec, sample_files=sample_files, full=full))
        except (OSError, ValueError, MemoryError, pa.ArrowException) as exc:
            reason = f"could not be compared: {type(exc).__name__}: {exc}"
            out.append(DatasetCheck(spec.source, spec.name, "skipped", reason))
    return out


__all__ = [
    "CHANGED_CELL",
    "LOST_TO_NULL",
    "ROW_EXTRA",
    "ROW_MISSING",
    "UNMAPPED_RAW_COLUMN",
    "DatasetCheck",
    "Loss",
    "RawSample",
    "csv_samples",
    "register_count_check",
    "register_raw_reader",
    "roundtrip_dataset",
    "roundtrip_lake",
]
