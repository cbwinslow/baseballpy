"""One small real request per provider (manual: ``uv run pytest tests/live -m live``).

The mocked suite proves the code against fixtures; these prove the fixtures still match the
providers. Each test fetches the least data that shows the path works, into a temporary lake.
"""

import pytest
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.sources.lahman.api import LahmanSource
from baseballpy.sources.mlb_api.api import MlbApiSource
from baseballpy.sources.mlb_api.endpoints import SUPPORTED
from baseballpy.sources.retrosheet.api import RetrosheetSource
from baseballpy.sources.statcast.extractor import StatcastExtractor

pytestmark = [pytest.mark.live, pytest.mark.enable_socket]


def test_statcast_one_day_of_pitches() -> None:
    table = StatcastExtractor().extract(start_date="2024-04-01", end_date="2024-04-01")
    assert table.num_rows > 1000
    assert {"game_pk", "pitch_type", "release_speed", "_extras"} <= set(table.column_names)


def test_mlb_teams_of_a_season() -> None:
    source = MlbApiSource()
    endpoint = next(e for e in SUPPORTED if e.name == "teams_season")
    report = source.endpoints.ingest(endpoint, source._context(2024, (1,)))
    assert report.rows == 30


def test_lahman_batting_from_the_permitted_mirror() -> None:
    table = LahmanSource().batting()
    assert table.num_rows > 100_000
    assert "HR" in table.column_names


def test_retrosheet_game_log_of_a_season() -> None:
    table = RetrosheetSource().game_logs(1990)
    assert table.num_rows >= 2000


def test_catalog_audit_finds_nothing_missing() -> None:
    result = CliRunner().invoke(main, ["catalog", "audit"])
    assert result.exit_code == 0, result.output
