"""Property tests proving MLB JSON flattening, typing and normalisation preserve values without loss."""

import datetime
import json
from typing import Any

import pyarrow as pa
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from baseballpy.core.config import QuarantineConfig
from baseballpy.core.quarantine import Quarantine
from baseballpy.core.schema_tools import EXTRAS, schema_from_columns
from baseballpy.sources.mlb_api.flatten import flatten_record, infer_type
from baseballpy.sources.mlb_api.generic import MlbRecordNormalizer

SETTINGS = settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


# ---------------------------------------------------------------------------
# 1. Integers: any JSON integer (including 64-bit and negatives) preserved
# ---------------------------------------------------------------------------

_INT_STRATEGY = st.one_of(
    st.integers(min_value=-100, max_value=100),
    st.integers(min_value=-2_000_000_000, max_value=2_000_000_000),
    st.integers(min_value=-(2**62), max_value=2**62),
)


@given(
    values=st.lists(
        st.one_of(_INT_STRATEGY, st.none()),
        min_size=1,
        max_size=25,
    ).filter(lambda lst: any(v is not None for v in lst))
)
@SETTINGS
def test_integers_preserved_without_loss(
    values: list[int | None], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Any JSON integer flattens to the same integer and stores with identical value."""
    for val in values:
        flat = flatten_record({"val": val})
        assert flat["val"] == val

    records = [{"val": v} for v in values]
    inferred = infer_type([r["val"] for r in records])
    assert inferred in ("int32", "int64")
    if any(v is not None and abs(v) > 2_000_000_000 for v in values):
        assert inferred == "int64"

    schema = schema_from_columns([("val", inferred)], extras=False)
    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q_int")))
    normalizer = MlbRecordNormalizer(quarantine=q)
    table = normalizer.from_records(records, schema, "test_integers")

    stored = table.column("val").to_pylist()
    assert len(stored) == len(values)
    for orig, actual in zip(values, stored, strict=True):
        if orig is None:
            assert actual is None
        else:
            assert actual == orig
            assert isinstance(actual, int)


# ---------------------------------------------------------------------------
# 2. Floats: finite JSON floats inferred as float64, never float32, == preserved
# ---------------------------------------------------------------------------

_FINITE_FLOATS = st.one_of(
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e12, max_value=1e12),
    st.sampled_from([85.8, 0.286, 1.0, -12.345, 99.99, 0.0, -0.0]),
)


@given(
    values=st.lists(
        st.one_of(_FINITE_FLOATS, st.none()),
        min_size=1,
        max_size=25,
    ).filter(lambda lst: any(v is not None for v in lst))
)
@SETTINGS
def test_floats_inferred_float64_and_preserved_exactly(
    values: list[float | None], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Finite JSON floats flatten and store with exact equality in float64 columns."""
    for val in values:
        flat = flatten_record({"speed": val})
        assert flat["speed"] == val

    records = [{"speed": v} for v in values]
    inferred = infer_type([r["speed"] for r in records])
    assert inferred == "float64"

    schema = schema_from_columns([("speed", inferred)], extras=False)
    assert schema.field("speed").type == pa.float64()

    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q_float")))
    normalizer = MlbRecordNormalizer(quarantine=q)
    table = normalizer.from_records(records, schema, "test_floats")

    assert table.schema.field("speed").type == pa.float64()
    stored = table.column("speed").to_pylist()
    for orig, actual in zip(values, stored, strict=True):
        if orig is None:
            assert actual is None
        else:
            assert actual == orig
            assert isinstance(actual, float)


def test_float32_would_fail_float_preservation() -> None:
    """Negative control showing float32 distorts decimal fractions like 85.8."""
    f32 = pa.array([85.8], type=pa.float32())[0].as_py()
    f64 = pa.array([85.8], type=pa.float64())[0].as_py()
    assert f32 != 85.8
    assert f64 == 85.8


# ---------------------------------------------------------------------------
# 3. Strings looking like numbers stay text and are stored character for character
# ---------------------------------------------------------------------------

_NUMBER_LIKE_SAMPLES = [
    ".286",
    "1.000",
    "007",
    "+5",
    "01405134",
    "1e3",
    "12345678901234567890",
    "0",
    "-001",
    "  .286  ",
    "  42  ",
    'He said "safe!"',
    "Ohtani 大谷",
    "Aaron Judge ⚾",
    "café",
]


@given(
    values=st.lists(
        st.sampled_from(_NUMBER_LIKE_SAMPLES),
        min_size=1,
        max_size=20,
    )
)
@SETTINGS
def test_number_like_strings_stay_text_and_preserved(
    values: list[str], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Number-like strings stay text and store character for character without conversion."""
    for val in values:
        flat = flatten_record({"text_col": val})
        assert flat["text_col"] == val

    records = [{"text_col": v} for v in values]
    inferred = infer_type([r["text_col"] for r in records])
    assert inferred == "string"

    schema = schema_from_columns([("text_col", inferred)], extras=False)
    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q_str")))
    normalizer = MlbRecordNormalizer(quarantine=q)
    table = normalizer.from_records(records, schema, "test_strings")

    assert table.schema.field("text_col").type == pa.string()
    stored = table.column("text_col").to_pylist()
    for orig, actual in zip(values, stored, strict=True):
        assert actual == orig
        assert isinstance(actual, str)


# ---------------------------------------------------------------------------
# 4. Booleans stay booleans (never 0/1 integers or words "true"/"false")
# ---------------------------------------------------------------------------


@given(
    values=st.lists(
        st.one_of(st.booleans(), st.none()),
        min_size=1,
        max_size=25,
    ).filter(lambda lst: any(v is not None for v in lst))
)
@SETTINGS
def test_booleans_stay_booleans(
    values: list[bool | None], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Booleans stay boolean and are never coerced to integers or text."""
    for val in values:
        flat = flatten_record({"flag": val})
        assert flat["flag"] is val

    records = [{"flag": v} for v in values]
    inferred = infer_type([r["flag"] for r in records])
    assert inferred == "bool"

    schema = schema_from_columns([("flag", inferred)], extras=False)
    assert schema.field("flag").type == pa.bool_()

    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q_bool")))
    normalizer = MlbRecordNormalizer(quarantine=q)
    table = normalizer.from_records(records, schema, "test_bools")

    assert table.schema.field("flag").type == pa.bool_()
    stored = table.column("flag").to_pylist()
    for orig, actual in zip(values, stored, strict=True):
        if orig is None:
            assert actual is None
        else:
            assert actual is orig
            assert type(actual) is bool
            assert actual not in ("true", "false", "True", "False")


# ---------------------------------------------------------------------------
# 5. Nulls and missing keys become NULL, empty string/list documented behavior
# ---------------------------------------------------------------------------


def test_nulls_missing_keys_and_empty_tokens_flatten_and_normalize(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """flatten.py preserves empty string while empty list -> None; generic.py normalizer maps empty string to NULL as documented."""
    # Level 1: flatten_record semantics
    flat = flatten_record(
        {
            "null_key": None,
            "empty_list": [],
            "empty_str": "",
            "valid_str": "hello",
        }
    )
    # As documented in flatten.py docstring: "lists become JSON text (empty list -> None)"
    assert flat["null_key"] is None
    assert flat["empty_list"] is None
    # Empty string in flatten_record is kept as ""
    assert flat["empty_str"] == ""
    assert flat["valid_str"] == "hello"

    # Level 2: normalizer semantics mapping onto schema
    records = [
        {"val": None},
        {},  # missing key
        {"val": ""},
        {"val": "hello"},
    ]
    # As documented in generic.py _as_string: "an empty string means no value (NULL), like every other source"
    schema = schema_from_columns([("val", "string")], extras=False)
    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q_null")))
    normalizer = MlbRecordNormalizer(quarantine=q)
    table = normalizer.from_records(records, schema, "test_nulls")

    stored = table.column("val").to_pylist()
    assert stored[0] is None  # null key -> NULL
    assert stored[1] is None  # missing key -> NULL
    assert stored[2] is None  # empty string -> NULL (per _as_string docstring & AGENTS.md 3B.5)
    assert stored[3] == "hello"  # non-empty string preserved


# ---------------------------------------------------------------------------
# 6. Nested objects flatten to dotted keys, arrays kept as JSON, extras preserved
# ---------------------------------------------------------------------------


@given(
    a=st.integers(min_value=-1000, max_value=1000),
    b=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8),
    c=st.booleans(),
    d=st.floats(allow_nan=False, allow_infinity=False, min_value=-100, max_value=100),
)
@SETTINGS
def test_nested_objects_flatten_to_dotted_leaves_once(a: int, b: str, c: bool, d: float) -> None:
    """Nested dicts flatten to dotted keys with each leaf present exactly once."""
    nested = {
        "team": {
            "id": a,
            "venue": {
                "name": b,
                "active": c,
            },
        },
        "score": d,
    }
    flat = flatten_record(nested)
    assert flat == {
        "team.id": a,
        "team.venue.name": b,
        "team.venue.active": c,
        "score": d,
    }


_LEAF_STRATEGY = st.one_of(
    st.integers(min_value=-1000, max_value=1000),
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz", max_size=6),
    st.booleans(),
    st.none(),
)


@given(items=st.lists(_LEAF_STRATEGY, min_size=1, max_size=10))
@SETTINGS
def test_arrays_kept_as_json_without_dropping_elements(
    items: list[Any], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Non-empty arrays are stored as compact JSON text whose json.loads equals the original."""
    flat = flatten_record({"events": items})
    raw_json = flat["events"]
    assert isinstance(raw_json, str)
    assert json.loads(raw_json) == items

    schema = schema_from_columns([("events", "string")], extras=False)
    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q_arr")))
    table = MlbRecordNormalizer(quarantine=q).from_records([flat], schema, "test_array")

    stored_json = table.column("events").to_pylist()[0]
    assert stored_json is not None
    assert json.loads(stored_json) == items


@given(
    known_id=st.integers(min_value=1, max_value=10000),
    extra_str=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    extra_num=st.integers(min_value=-500, max_value=500),
)
@SETTINGS
def test_unknown_columns_end_up_in_extras_without_loss(
    known_id: int, extra_str: str, extra_num: int, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Fields not declared in schema end up in _extras column with values intact."""
    records = [{"player_id": known_id, "unknown_text": extra_str, "unknown_metric": extra_num}]
    schema = schema_from_columns([("player_id", "int32")], extras=True)
    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q_ext")))
    normalizer = MlbRecordNormalizer(quarantine=q)
    table = normalizer.from_records(records, schema, "test_extras")

    assert EXTRAS in table.column_names
    assert table.column("player_id").to_pylist() == [known_id]

    extras_val = table.column(EXTRAS).to_pylist()[0]
    assert extras_val is not None
    parsed = json.loads(extras_val)
    assert parsed == {"unknown_metric": extra_num, "unknown_text": extra_str}


# ---------------------------------------------------------------------------
# 7. Dates and timestamps render back to same date/instant (no day or tz shift)
# ---------------------------------------------------------------------------


@given(
    d=st.dates(
        min_value=datetime.date(1871, 1, 1),
        max_value=datetime.date(2100, 12, 31),
    )
)
@SETTINGS
def test_dates_inferred_date32_and_render_without_day_shift(
    d: datetime.date, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """ISO dates inferred as date32 render back to exact date without day shift."""
    date_str = d.isoformat()
    flat = flatten_record({"game_date": date_str})
    assert flat["game_date"] == date_str

    inferred = infer_type([date_str])
    assert inferred == "date32"

    schema = schema_from_columns([("game_date", inferred)], extras=False)
    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q_date")))
    normalizer = MlbRecordNormalizer(quarantine=q)
    table = normalizer.from_records([flat], schema, "test_dates")

    stored = table.column("game_date").to_pylist()[0]
    assert isinstance(stored, datetime.date)
    assert stored == d
    assert stored.isoformat() == date_str


@given(
    dt=st.datetimes(
        min_value=datetime.datetime(1970, 1, 1),
        max_value=datetime.datetime(2038, 1, 1),
        timezones=st.just(datetime.UTC),
    )
)
@SETTINGS
def test_utc_timestamps_inferred_and_render_without_instant_shift(
    dt: datetime.datetime, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """UTC ISO timestamps inferred as timestamp render back to the exact instant."""
    dt = dt.replace(microsecond=0)  # the text carries whole seconds
    ts_str = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    flat = flatten_record({"event_time": ts_str})
    assert flat["event_time"] == ts_str

    inferred = infer_type([ts_str])
    assert inferred == "timestamp"

    schema = schema_from_columns([("event_time", inferred)], extras=False)
    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q_ts")))
    normalizer = MlbRecordNormalizer(quarantine=q)
    table = normalizer.from_records([flat], schema, "test_timestamps")

    stored = table.column("event_time").to_pylist()[0]
    assert isinstance(stored, datetime.datetime)
    assert stored.timestamp() == dt.timestamp()
    assert stored == dt


def test_offset_timestamps_preserve_exact_instant(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Timestamps with non-UTC offset preserve the exact instant in UTC."""
    ts_str = "2024-06-23T15:05:00-04:00"
    flat = flatten_record({"event_time": ts_str})
    assert flat["event_time"] == ts_str

    inferred = infer_type([ts_str])
    assert inferred == "timestamp"

    schema = schema_from_columns([("event_time", inferred)], extras=False)
    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q_ts_off")))
    normalizer = MlbRecordNormalizer(quarantine=q)
    table = normalizer.from_records([flat], schema, "test_offset_ts")

    stored = table.column("event_time").to_pylist()[0]
    expected = datetime.datetime.fromisoformat(ts_str)
    assert isinstance(stored, datetime.datetime)
    assert stored.timestamp() == expected.timestamp()
    assert stored == expected.astimezone(datetime.UTC)


@given(
    dt=st.datetimes(
        min_value=datetime.datetime(1970, 1, 1),
        max_value=datetime.datetime(2038, 1, 1),
        timezones=st.just(datetime.UTC),
    )
)
@SETTINGS
def test_fractional_second_timestamps_keep_their_microseconds(
    dt: datetime.datetime, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """MLB play-by-play times carry fractions of a second (for example ...:07:30.123Z): none may be rounded away."""
    ts_str = dt.isoformat().replace("+00:00", "Z")
    flat = flatten_record({"event_time": ts_str})
    assert flat["event_time"] == ts_str
    inferred = infer_type([ts_str])
    assert inferred == "timestamp"
    schema = schema_from_columns([("event_time", inferred)], extras=False)
    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q_ts_frac")))
    table = MlbRecordNormalizer(quarantine=q).from_records([flat], schema, "test_fractional")
    stored = table.column("event_time").to_pylist()[0]
    assert stored == dt, f"{ts_str} was stored as {stored.isoformat()}"
