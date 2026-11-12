"""The type audits: no hard-coded probe seasons, and text columns that hold only numbers or dates are found.

Change typing-gaps-retrosheet-statcast. The generator and the audit are dev scripts, loaded by path.
"""

import importlib.util
from datetime import date
from pathlib import Path
from types import ModuleType

import duckdb

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_savant_generator_probes_every_season_not_a_fixed_list() -> None:
    from baseballpy.sources.statcast.seasons import FIRST_SEASON

    generator = _load("gen_savant_schemas")
    assert not hasattr(generator, "SAMPLE_YEARS"), "a hard-coded list of probe seasons"
    assert generator.probe_years(date(2026, 6, 1)) == tuple(range(FIRST_SEASON, 2027))
    assert generator.probe_years(date(2009, 1, 1)) == (2008, 2009)


def test_text_columns_that_hold_only_numbers_or_dates_are_found() -> None:
    audit = _load("audit_column_types")
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE t AS SELECT * FROM (VALUES "
        "('1', '1.5', '20240401', '010020000', 'abc', '2024-04-01'), "
        "('-7', '2', '20240402', '000000010', '12', '2024-04-02'), "
        "(NULL, '0.25', '20240403', '3', NULL, NULL), "
        "('42', NULL, '20240404', '000', 'x1', '2024-04-04')"
        ") AS v(whole, decimal, packed_date, line_score, mixed, iso_date)"
    )
    found = {
        f.column: f.kind
        for f in audit.find_typed_text_columns(
            con,
            "t",
            ["whole", "decimal", "packed_date", "line_score", "mixed", "iso_date"],
            min_values=3,
        )
    }
    assert found == {
        "whole": "int",
        "decimal": "float",
        "packed_date": "date",
        "iso_date": "date",
    }, "leading zeros (line scores) and mixed text stay text"


def test_a_season_where_a_column_is_empty_gives_no_type_evidence() -> None:
    """2008-2015 send some leaderboard columns completely empty; an empty column must not widen the type to text."""
    generator = _load("gen_savant_schemas")
    assert generator.observed_type(["", None, ""]) is None
    assert generator.observed_type([]) is None
    assert generator.observed_type(["1.5", "", "2.25"]) == "float64"
    assert generator.observed_type(["3", "-7"]) == "int16"
    assert generator.observed_type(["abc", ""]) == "string"
    widened = generator.widen("float64", generator.observed_type(["", ""]) or "float64")
    assert widened == "float64"
