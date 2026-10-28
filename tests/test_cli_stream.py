"""Tests for CLI live game event streaming command."""

import json
from collections.abc import AsyncIterator, Generator
from pathlib import Path

import duckdb
import pytest
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.core.config import reset_config
from baseballpy.sources.mlb_api.stream import LiveEvent


class FakeLiveStreamer:
    """Test streamer emitting prefabricated LiveEvent instances."""

    def __init__(
        self,
        events: list[LiveEvent],
        error: Exception | None = None,
    ) -> None:
        self.events = events
        self.error = error
        self.last_resume: bool | None = None

    async def stream_live_events(
        self, game_pk: int, resume: bool = True
    ) -> AsyncIterator[LiveEvent]:
        """Yield fabricated events and optionally raise a test exception."""
        self.last_resume = resume
        for ev in self.events:
            yield ev
        if self.error is not None:
            raise self.error


def _sample_events() -> list[LiveEvent]:
    return [
        LiveEvent(
            game_pk=716462,
            at_bat_index=0,
            event_index=0,
            event_kind="pitch",
            is_pitch=True,
            pitch_type="FF",
            start_speed=96.4,
            description="Called Strike",
            balls=0,
            strikes=1,
            outs=0,
            inning=1,
            is_top_inning=True,
        ),
        LiveEvent(
            game_pk=716462,
            at_bat_index=0,
            event_index=1,
            event_kind="pitch",
            is_pitch=True,
            pitch_type="SL",
            start_speed=87.1,
            description="Swinging Strike",
            balls=0,
            strikes=2,
            outs=0,
            inning=1,
            is_top_inning=True,
        ),
    ]


@pytest.fixture(autouse=True)
def isolated_lake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Isolate lake home directory with temporary BASEBALLPY_HOME."""
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path))
    reset_config()
    yield
    reset_config()


@pytest.fixture
def runner() -> CliRunner:
    """Fixture providing a Click CliRunner."""
    return CliRunner()


def test_stream_events_printed(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify events and summary line are printed to console when no destination is given."""
    fake_streamer = FakeLiveStreamer(_sample_events())
    monkeypatch.setattr("baseballpy.cli_stream.make_streamer", lambda _: fake_streamer)

    result = runner.invoke(main, ["stream", "716462"])
    assert result.exit_code == 0, result.output
    assert "PITCH" in result.output
    assert "Called Strike" in result.output
    assert "Swinging Strike" in result.output
    assert "2 events seen, 0 events written" in result.output


def test_stream_jsonl_written(
    tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify events are persisted to a JSONL file destination."""
    jsonl_file = tmp_path / "events.jsonl"
    fake_streamer = FakeLiveStreamer(_sample_events())
    monkeypatch.setattr("baseballpy.cli_stream.make_streamer", lambda _: fake_streamer)

    result = runner.invoke(main, ["stream", "716462", "--jsonl", str(jsonl_file)])
    assert result.exit_code == 0, result.output
    assert jsonl_file.is_file()

    lines = [
        json.loads(line)
        for line in jsonl_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 2
    assert lines[0]["game_pk"] == 716462
    assert lines[0]["event_index"] == 0
    assert "2 events seen, 2 events written" in result.output


def test_stream_duckdb_upsert_idempotent(
    tmp_path: Path, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify running the same stream twice into DuckDB leaves the exact same row count."""
    duckdb_file = tmp_path / "stream.duckdb"
    fake_streamer = FakeLiveStreamer(_sample_events())
    monkeypatch.setattr("baseballpy.cli_stream.make_streamer", lambda _: fake_streamer)

    res1 = runner.invoke(main, ["stream", "716462", "--duckdb", str(duckdb_file), "--replay"])
    assert res1.exit_code == 0, res1.output

    con = duckdb.connect(database=str(duckdb_file))
    try:
        assert con.execute("SELECT count(*) FROM live_events").fetchone()[0] == 2
    finally:
        con.close()

    res2 = runner.invoke(main, ["stream", "716462", "--duckdb", str(duckdb_file), "--replay"])
    assert res2.exit_code == 0, res2.output

    con = duckdb.connect(database=str(duckdb_file))
    try:
        assert con.execute("SELECT count(*) FROM live_events").fetchone()[0] == 2
    finally:
        con.close()


def test_stream_max_events(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify stream halts after max-events threshold is reached."""
    events = _sample_events() + _sample_events()
    fake_streamer = FakeLiveStreamer(events)
    monkeypatch.setattr("baseballpy.cli_stream.make_streamer", lambda _: fake_streamer)

    result = runner.invoke(main, ["stream", "716462", "--max-events", "1"])
    assert result.exit_code == 0, result.output
    assert "1 events seen" in result.output


def test_stream_exception_path(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify exceptions from the stream propagate cleanly as ClickException."""
    fake_streamer = FakeLiveStreamer([], error=RuntimeError("Gameday connection reset"))
    monkeypatch.setattr("baseballpy.cli_stream.make_streamer", lambda _: fake_streamer)

    result = runner.invoke(main, ["stream", "716462"])
    assert result.exit_code != 0
    assert "Gameday connection reset" in result.output


def test_stream_as_json_stdout(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify --json emits newline-delimited JSON objects to stdout."""
    fake_streamer = FakeLiveStreamer(_sample_events())
    monkeypatch.setattr("baseballpy.cli_stream.make_streamer", lambda _: fake_streamer)

    result = runner.invoke(main, ["stream", "716462", "--json"])
    assert result.exit_code == 0, result.output
    lines = [json.loads(line) for line in result.output.strip().splitlines() if line.strip()]
    assert len(lines) == 2
    assert lines[0]["game_pk"] == 716462
    assert lines[1]["pitch_type"] == "SL"


def test_live_event_schema_covers_every_to_dict_key_with_declared_types() -> None:
    from baseballpy.cli_stream import live_event_schema

    event = LiveEvent(game_pk=1, at_bat_index=0, event_index=0, event_kind="game_status")
    schema = live_event_schema()
    assert schema.names == list(event.to_dict())
    assert str(schema.field("start_speed").type) == "double"
    assert str(schema.field("ts_utc").type) == "int64"
    assert str(schema.field("is_pitch").type) == "bool"
