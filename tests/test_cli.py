"""CLI tests (click CliRunner)."""

from click.testing import CliRunner

from baseballpy.cli import main


def test_licenses_flag_lists_every_source() -> None:
    result = CliRunner().invoke(main, ["--licenses"])
    assert result.exit_code == 0
    for needle in ("GPL-3.0-or-later", "Retrosheet", "Lahman", "Chadwick", "MLB"):
        assert needle in result.output


def test_help_lists_commands() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "statcast" in result.output and "audit" in result.output
