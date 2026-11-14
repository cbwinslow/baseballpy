"""Property tests proving casting and normalization never silently change or drop values."""

import datetime
import json
import math
from typing import Any

import pyarrow as pa
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from baseballpy.core.coerce import NULL_TOKENS, CoercionError, to_bool, to_date, to_float, to_int
from baseballpy.core.config import QuarantineConfig
from baseballpy.core.quarantine import Quarantine, checked_cast, safe_array
from baseballpy.core.schema_tools import (
    EXTRAS,
    infer_type_name,
    map_to_schema,
    pack_extras,
    schema_from_columns,
)

SETTINGS = settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


def _count_quarantined_records(quarantine: Quarantine) -> int:
    """Count all dead-letter records written to .jsonl files in quarantine."""
    base_dir = quarantine.config.quarantine_dir
    if not base_dir.is_dir():
        return 0
    total = 0
    for path in base_dir.rglob("*.jsonl"):
        with open(path, encoding="utf-8") as handle:
            total += sum(1 for line in handle if line.strip())
    return total


# ---------------------------------------------------------------------------
# 1. Integers without a leading zero or plus sign
# ---------------------------------------------------------------------------


@given(
    values=st.lists(
        st.one_of(
            st.integers(min_value=-(2**62), max_value=2**62).map(str),
            st.none(),
            st.just(""),
        ),
        min_size=1,
        max_size=30,
    ).filter(lambda lst: any(v not in (None, "") for v in lst))
)
@SETTINGS
def test_integers_without_leading_zeros_preserved(
    values: list[str | None], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Integers without leading zero or plus sign are inferred as integer type and round-trip."""
    inferred = infer_type_name(values)
    assert inferred in ("int16", "int32", "int64")

    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q")))
    schema = schema_from_columns([("val", inferred)], extras=False)
    table = pa.table({"val": pa.array(values, type=pa.string())})
    out = map_to_schema(table, schema, source="test", dataset="integers", quarantine=q)

    stored_col = out.column("val").to_pylist()
    for raw, stored in zip(values, stored_col, strict=True):
        if raw is None or raw == "":
            assert stored is None
        else:
            assert stored is not None
            assert str(stored) == raw.strip()


# ---------------------------------------------------------------------------
# 2. Codes: digits starting with 0 (len >= 2) or starting with +
# ---------------------------------------------------------------------------

_DIGITS = st.text(alphabet="0123456789", min_size=1, max_size=10)
CODE_STRINGS = st.one_of(
    st.builds(lambda d: f"0{d}", _DIGITS),  # e.g. "01405134", "007"
    st.builds(lambda d: f"+{d}", _DIGITS),  # e.g. "+5", "+100"
)


@given(
    code_val=CODE_STRINGS,
    other_vals=st.lists(
        st.one_of(
            st.integers(min_value=-10000, max_value=10000).map(str),
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz", max_size=8),
            st.none(),
        ),
        max_size=15,
    ),
)
@SETTINGS
def test_code_strings_inferred_as_string_and_preserved(
    code_val: str, other_vals: list[str | None], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Codes starting with '0' (len >= 2) or '+' force string type and keep leading digits."""
    values: list[str | None] = [code_val, *other_vals]
    inferred = infer_type_name(values)
    assert inferred == "string"

    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q")))
    schema = schema_from_columns([("code_col", inferred)], extras=False)
    table = pa.table({"code_col": pa.array(values, type=pa.string())})
    out = map_to_schema(table, schema, source="test", dataset="codes", quarantine=q)

    stored_col = out.column("code_col").to_pylist()
    for raw, stored in zip(values, stored_col, strict=True):
        assert stored == raw


# ---------------------------------------------------------------------------
# 3. Decimals: inferred as float64, stored value equals float(text) exactly
# ---------------------------------------------------------------------------

DECIMAL_STRINGS = st.tuples(
    st.integers(min_value=-1_000_000, max_value=1_000_000),
    st.integers(min_value=1, max_value=999_999),
).map(lambda pair: f"{pair[0]}.{pair[1]}")


@given(
    decimals=st.lists(DECIMAL_STRINGS, min_size=1, max_size=25),
    nulls=st.lists(st.none(), max_size=5),
)
@SETTINGS
def test_decimals_inferred_float64_and_preserved_exactly(
    decimals: list[str], nulls: list[None], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Decimals are inferred as float64 (never float32) and match float(text) exactly."""
    values: list[str | None] = [*decimals, *nulls]
    inferred = infer_type_name(values)
    assert inferred == "float64"

    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q")))
    schema = schema_from_columns([("dec_col", inferred)], extras=False)
    table = pa.table({"dec_col": pa.array(values, type=pa.string())})
    out = map_to_schema(table, schema, source="test", dataset="decimals", quarantine=q)

    stored_col = out.column("dec_col").to_pylist()
    for raw, stored in zip(values, stored_col, strict=True):
        if raw is None:
            assert stored is None
        else:
            expected = float(raw)
            assert stored == expected


def test_32_bit_float_would_fail_decimal_preservation() -> None:
    """Demonstrate why float32 is forbidden: '85.8' distorts to 85.80000305175781."""
    f32_val = pa.array(["85.8"]).cast(pa.float32())[0].as_py()
    f64_val = pa.array(["85.8"]).cast(pa.float64())[0].as_py()
    assert f32_val != 85.8
    assert f64_val == 85.8


# ---------------------------------------------------------------------------
# 4. Conservation: output_nulls == input_nulls + quarantined
# ---------------------------------------------------------------------------

ARBITRARY_CELLS = st.sampled_from(
    [
        "0",
        "7",
        "  7 ",
        "-42",
        "7.0",
        "157.0",
        "40000",
        "-40000",
        "1e3",
        "85.8",
        "-12.345",
        "2024-01-15",
        "1999-12-31",
        "bad-date",
        "2024-99-99",
        "abc",
        "not_a_num",
        "--",
        "N/A",
        "",
        None,
    ]
)
TARGET_TYPES = st.sampled_from([pa.int16(), pa.int32(), pa.float64(), pa.date32()])


@given(
    values=st.lists(ARBITRARY_CELLS, max_size=20),
    target=TARGET_TYPES,
)
@SETTINGS
def test_conservation_checked_cast_never_changes_or_drops(
    values: list[str | None], target: pa.DataType, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Checked cast stores value equal to parsed value or sends it to quarantine (no silent loss)."""
    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q")))
    arr = pa.array(values, type=pa.string())
    out = checked_cast(arr, target, quarantine=q, source="s", dataset="d", column="c")

    stored = out.to_pylist()
    input_nulls = sum(1 for v in values if v is None)
    output_nulls = sum(1 for v in stored if v is None)
    quarantined = _count_quarantined_records(q)

    assert output_nulls == input_nulls + quarantined

    for orig, val in zip(values, stored, strict=True):
        if val is not None:
            assert orig is not None
            if pa.types.is_integer(target):
                assert val == int(orig)
            elif pa.types.is_floating(target):
                assert val == float(orig) or (math.isnan(val) and math.isnan(float(orig)))
            elif pa.types.is_date32(target):
                assert val == datetime.date.fromisoformat(orig.strip())


@given(
    values=st.lists(
        st.one_of(
            st.integers(min_value=-50000, max_value=50000),
            st.sampled_from(["40000", "-40000", "1e3", "  7 ", "7.0", "xyz", None]),
        ),
        max_size=20,
    ),
    target=st.sampled_from([pa.int16(), pa.int32(), pa.float64()]),
)
@SETTINGS
def test_conservation_safe_array_never_changes_or_drops(
    values: list[Any], target: pa.DataType, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Safe array either coerces value or quarantines it, preserving null conservation."""
    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q")))
    out = safe_array(values, target, source="s", dataset="d", column="c", quarantine=q)

    stored = out.to_pylist()
    input_nulls = sum(1 for v in values if v is None or (isinstance(v, str) and not v.strip()))
    output_nulls = sum(1 for v in stored if v is None)
    quarantined = _count_quarantined_records(q)

    assert output_nulls == input_nulls + quarantined


# ---------------------------------------------------------------------------
# 5. Unknown columns: end up in _extras (JSON) without loss
# ---------------------------------------------------------------------------


@given(
    known_data=st.lists(
        st.tuples(st.integers(min_value=1, max_value=1000).map(str), st.text(max_size=6)),
        min_size=1,
        max_size=15,
    ),
    extra_data=st.lists(
        st.tuples(
            st.one_of(st.text(max_size=8), st.none()),
            st.one_of(st.text(max_size=8), st.none()),
        ),
        min_size=1,
        max_size=15,
    ),
)
@SETTINGS
def test_unknown_columns_end_up_in_extras_without_loss(
    known_data: list[tuple[str, str]],
    extra_data: list[tuple[str | None, str | None]],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Columns not declared in the schema are serialized into _extras with no cells dropped."""
    num_rows = min(len(known_data), len(extra_data))
    known_slice = known_data[:num_rows]
    extra_slice = extra_data[:num_rows]

    col_id = [r[0] for r in known_slice]
    col_name = [r[1] for r in known_slice]
    col_unk1 = [r[0] for r in extra_slice]
    col_unk2 = [r[1] for r in extra_slice]

    table = pa.Table.from_arrays(
        [
            pa.array(col_id, type=pa.string()),
            pa.array(col_name, type=pa.string()),
            pa.array(col_unk1, type=pa.string()),
            pa.array(col_unk2, type=pa.string()),
        ],
        names=["id", "name", "unk_field_1", "unk_field_2"],
    )

    schema = schema_from_columns([("id", "int32"), ("name", "string")], extras=True)
    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q")))
    out = map_to_schema(table, schema, source="s", dataset="d", quarantine=q)

    assert EXTRAS in out.column_names
    extras_values = out.column(EXTRAS).to_pylist()

    for idx, (u1, u2) in enumerate(zip(col_unk1, col_unk2, strict=True)):
        expected_dict: dict[str, str] = {}
        if u1 is not None:
            expected_dict["unk_field_1"] = u1
        if u2 is not None:
            expected_dict["unk_field_2"] = u2

        actual_cell = extras_values[idx]
        if not expected_dict:
            assert actual_cell is None
        else:
            assert actual_cell is not None
            assert json.loads(actual_cell) == expected_dict

    direct_extras = pack_extras(
        table, ["unk_field_1", "unk_field_2"], source="s", dataset="d"
    ).to_pylist()
    assert direct_extras == extras_values


# ---------------------------------------------------------------------------
# 6. NULL tokens: documented NULL_TOKENS become NULL and nothing else does
# ---------------------------------------------------------------------------


@given(text=st.text(max_size=15))
@SETTINGS
def test_null_tokens_coercion_and_non_null_preservation(text: str) -> None:
    """Documented NULL_TOKENS become NULL, while non-null-tokens never silently return NULL."""
    is_null_token = text.strip() in NULL_TOKENS

    for fn in (to_int, to_float, to_bool, to_date):
        if is_null_token:
            assert fn(text) is None
        else:
            try:
                res = fn(text)
            except CoercionError:
                pass
            else:
                assert res is not None, f"{fn.__name__}({text!r}) silently returned None"


def test_specific_non_null_tokens_not_null() -> None:
    """Explicitly verify that '0' and '-' (when not a null token) never become NULL."""
    # '0' is not in NULL_TOKENS: must convert, never become None
    assert to_int("0") == 0
    assert to_float("0") == 0.0
    assert to_bool("0") is False
    with pytest.raises(CoercionError):
        to_date("0")

    # When '-' is excluded from null tokens, it must raise CoercionError, not return None
    strict_nulls = frozenset({""})
    with pytest.raises(CoercionError):
        to_int("-", nulls=strict_nulls)
    with pytest.raises(CoercionError):
        to_float("-", nulls=strict_nulls)
    with pytest.raises(CoercionError):
        to_bool("-", nulls=strict_nulls)
    with pytest.raises(CoercionError):
        to_date("-", nulls=strict_nulls)
