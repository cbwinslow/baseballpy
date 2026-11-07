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
