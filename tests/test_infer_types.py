"""Type inference for the schema generators: the narrowest exact type that holds every sample."""

from baseballpy.core.infer_types import decimal_type, infer


def test_integers_text_numbers_and_identifiers() -> None:
    assert infer([1, 2, None]) == "int32"
    assert infer([3_000_000_000]) == "int64"
    assert infer(["12", "7"]) == "int32"
    assert infer(["007"]) == "string", "a leading zero is an identifier, not a number"
    token = "4190999863501015539231959302839752501024819861460260944189915459092804112342"  # noqa: S105 - a public outcome token id, not a secret
    assert infer([token]) == "string", "a number that does not fit 64 bits is text"
    assert infer([int(token)]) == "string"


def test_decimals_times_and_flags() -> None:
    assert infer(["0.5400", "1.0000"]) == "decimal(9,4)"
    assert infer(["1234567.50"]) == "decimal(18,2)"
    assert decimal_type(["0.5"]) == "decimal(9,1)"
    assert infer(["2026-10-28T05:25:00Z"]) == "timestamp"
    assert infer(["2024-09-28 14:50:48+00"]) == "timestamp"
    assert infer(["2026-10-28"]) == "date32"
    assert infer([True, False]) == "bool"
    assert infer([True, 1]) == "string"
    assert infer([None, ""]) == "string"


def test_json_numbers_stay_floats_unless_asked_and_short_enough() -> None:
    assert infer([0.9965, 1]) == "float64"
    assert infer([0.9965, 0.5], floats_as_decimal=True) == "decimal(9,4)"
    assert infer([0.12345678901], floats_as_decimal=True) == "float64"
    assert infer([1e-07], floats_as_decimal=True) == "float64"


def test_leading_dot_decimals_and_whole_numbers_written_as_floats() -> None:
    assert infer([".316", ".313", "-.412"]) == "decimal(9,3)"
    assert infer(["592450.0", "16.0"], max_text_scale=8) == "int32"
    assert infer(["592450.0", "16.5"], max_text_scale=8) == "decimal(18,1)"
    assert infer(["592450.0"]) == "decimal(18,1)", "without the option the text type is kept"


def test_ids_written_both_as_plain_and_as_float_text_are_one_integer_type() -> None:
    assert infer(["110587", "687060.0"], max_text_scale=8) == "int32"


def test_a_whole_number_written_with_a_zero_fraction_loads_as_that_integer() -> None:
    import pyarrow as pa

    from baseballpy.core.schema_tools import normalize_csv, schema_from_columns

    schema = schema_from_columns([("ab", "int32"), ("id", "int32")])
    table = normalize_csv(
        b"ab,id\n157.0,110587\n12,687060.0\n,5\n", schema, source="x", dataset="y"
    )
    assert table.column("ab").to_pylist() == [157, 12, None]
    assert table.column("id").to_pylist() == [110587, 687060, 5]
    bad = normalize_csv(b"ab,id\n12.5,1\n", schema, source="x", dataset="y")
    assert bad.column("ab").to_pylist() == [None], "a real fraction is still refused, not rounded"
    assert isinstance(table.schema.field("ab").type, pa.DataType)


def test_long_or_scientific_numbers_in_text_are_floats_when_asked() -> None:
    assert infer(["0.2857142857142857", "1.5"], max_text_scale=8) == "float64"
    assert infer(["1.5e-05", "2"], max_text_scale=8) == "float64"
    assert infer(["0.285", "1.5"], max_text_scale=8) == "decimal(9,3)"
    assert infer(["0.2857142857142857"]) == "decimal(38,16)", "without the option, exact decimals"


def test_numbers_with_leading_zeros_or_a_plus_sign_are_text() -> None:
    """Identifiers such as the NPB id 01405134 are not numbers: a number type would drop the zeros (round-trip check)."""
    from baseballpy.core.schema_tools import infer_type_name

    assert infer_type_name(["01405134", "03905157", "7"]) == "string"
    assert infer_type_name(["007", None]) == "string"
    assert infer_type_name(["+5", "6"]) == "string"
    assert infer_type_name(["01.5", "2.5"]) == "string", "a decimal with a leading zero is text too"
    # these are plain numbers and stay numbers
    assert infer_type_name(["0", "-7", "12"]) == "int16"
    assert infer_type_name(["0.5", "-0.25", "10"]) == "float64"
    assert infer_type_name(["0", "100000"]) == "int32"
