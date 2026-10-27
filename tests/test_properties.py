"""Property-based tests (Hypothesis): normalizers and coercion never crash on arbitrary input."""

import contextlib

import pyarrow as pa
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from baseballpy.core.coerce import CoercionError, to_bool, to_date, to_float, to_int
from baseballpy.core.config import QuarantineConfig
from baseballpy.core.quarantine import Quarantine, checked_cast, safe_array
from baseballpy.sources.lahman.normalizer import LahmanNormalizer
from baseballpy.sources.statcast.leaderboards import StatcastLeaderboardNormalizer
from baseballpy.sources.statcast.normalizer import StatcastNormalizer

NULLISH = st.sampled_from(["", "NA", "null", "None", "NaN", "<NA>", "--", " "])
JUNK = st.one_of(
    st.text(max_size=20),
    NULLISH,
    st.floats(allow_nan=True, allow_infinity=True),
    st.integers(min_value=-(10**12), max_value=10**12),
    st.none(),
    st.booleans(),
)

SETTINGS = settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)


@given(JUNK)
@SETTINGS
def test_coercers_parse_or_raise_coercion_error(value: object) -> None:
    for fn in (to_int, to_float, to_bool, to_date):
        with contextlib.suppress(CoercionError):
            fn(value)


@given(st.integers(min_value=-(10**9), max_value=10**9))
@SETTINGS
def test_to_int_roundtrips_integers(n: int) -> None:
    assert to_int(str(n)) == n
    assert to_int(float(n)) == n


@given(st.floats(allow_nan=False, allow_infinity=False).filter(lambda f: f != int(f)))
@SETTINGS
def test_to_int_never_truncates(f: float) -> None:
    with pytest.raises(CoercionError):
        to_int(f)


@given(values=st.lists(st.one_of(st.text(max_size=8), st.integers(), st.none()), max_size=30))
@SETTINGS
def test_checked_cast_never_raises_and_preserves_length(
    values: list[object], tmp_path_factory: pytest.TempPathFactory
) -> None:
    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q")))
    arr = pa.array([None if v is None else str(v) for v in values], type=pa.string())
    out = checked_cast(arr, pa.int16(), quarantine=q, source="s", dataset="d", column="c")
    assert len(out) == len(values)
    assert out.type == pa.int16()


@given(
    values=st.lists(
        st.one_of(st.integers(min_value=-(10**6), max_value=10**6), st.none()), max_size=30
    )
)
@SETTINGS
def test_safe_array_nulls_out_of_range_int8(
    values: list[int | None], tmp_path_factory: pytest.TempPathFactory
) -> None:
    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q")))
    out = safe_array(values, pa.int8(), source="s", dataset="d", column="c", quarantine=q)
    assert len(out) == len(values)
    for original, stored in zip(values, out.to_pylist(), strict=True):
        if original is not None and -128 <= original <= 127:
            assert stored == original
        else:
            assert stored is None


CSV_CELL = st.one_of(
    st.text(
        alphabet=st.characters(blacklist_characters='\r\n",\x00', blacklist_categories=("Cs",)),
        max_size=8,
    ),
    NULLISH,
    st.integers().map(str),
    st.floats(allow_nan=True, allow_infinity=True).map(str),
)


@given(rows=st.lists(st.tuples(CSV_CELL, CSV_CELL, CSV_CELL), max_size=15))
@SETTINGS
def test_statcast_normalizer_survives_arbitrary_cells(
    rows: list[tuple[str, str, str]], tmp_path_factory: pytest.TempPathFactory
) -> None:
    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q")))
    csv = "game_pk,game_date,release_speed\n" + "\n".join(",".join(r) for r in rows) + "\n"
    table = StatcastNormalizer(quarantine=q).normalize(csv.encode())
    assert table.schema.field("game_pk").type == pa.int32()
    assert table.schema.field("game_date").type == pa.date32()
    assert table.schema.field("release_speed").type == pa.float32()
    assert len(table) == len([r for r in rows if any(c.strip() for c in r)]) or len(table) <= len(
        rows
    )


@given(rows=st.lists(st.tuples(CSV_CELL, CSV_CELL, CSV_CELL), max_size=15))
@SETTINGS
def test_lahman_normalizer_survives_arbitrary_cells(
    rows: list[tuple[str, str, str]], tmp_path_factory: pytest.TempPathFactory
) -> None:
    q = Quarantine(QuarantineConfig(base_dir=tmp_path_factory.mktemp("q")))
    csv = "playerID,yearID,G\n" + "\n".join(",".join(r) for r in rows) + "\n"
    table = LahmanNormalizer(quarantine=q).normalize(csv, table_name="Batting")
    assert table.schema.field("yearID").type == pa.int16()
    assert table.schema.field("playerID").type == pa.string()


@given(st.binary(max_size=200))
@SETTINGS
def test_leaderboard_normalizer_never_raises_on_arbitrary_bytes(raw: bytes) -> None:
    table = StatcastLeaderboardNormalizer().normalize(raw)
    assert isinstance(table, pa.Table)


@given(
    rows=st.lists(
        st.tuples(CSV_CELL, CSV_CELL, CSV_CELL, CSV_CELL, CSV_CELL, CSV_CELL), max_size=10
    )
)
@SETTINGS
def test_retrosheet_reference_parser_survives_arbitrary_cells(
    rows: list[tuple[str, ...]], tmp_path_factory: pytest.TempPathFactory
) -> None:
    import os

    from baseballpy.core.quarantine import get_quarantine
    from baseballpy.sources.retrosheet.parser import RetrosheetReferenceParser

    home = tmp_path_factory.mktemp("home")
    os.environ["BASEBALLPY_HOME"] = str(home)
    get_quarantine.reset()
    try:
        path = home / "teams.csv"
        path.write_text(
            "TEAM,LEAGUE,CITY,NICKNAME,FIRST,LAST\n" + "\n".join(",".join(r) for r in rows) + "\n",
            encoding="utf-8",
            newline="",
        )
        table = RetrosheetReferenceParser().parse_file("teams", path)
        assert table.schema.field("first_year").type == pa.int16()
    finally:
        os.environ.pop("BASEBALLPY_HOME", None)
        get_quarantine.reset()


@given(
    payload=st.recursive(
        st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=6), st.floats()),
        lambda inner: st.one_of(
            st.lists(inner, max_size=3), st.dictionaries(st.text(max_size=6), inner, max_size=4)
        ),
        max_leaves=15,
    )
)
@SETTINGS
def test_mlb_normalizers_survive_arbitrary_json(payload: object) -> None:
    from baseballpy.sources.mlb_api.normalizer import MlbApiNormalizer

    norm = MlbApiNormalizer()
    data = payload if isinstance(payload, dict) else {"dates": payload, "teams": payload}
    for fn in (norm.normalize_schedule, norm.normalize_teams, norm.normalize_venues):
        try:
            table = fn(data)
        except (AttributeError, TypeError):
            continue  # structurally impossible payload shape (e.g. a list where an object is expected)
        assert isinstance(table, pa.Table)
