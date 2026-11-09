"""Tests for CLI live game event streaming command."""

import json
from collections.abc import AsyncIterator, Generator
from pathlib import Path

import duckdb
import httpx
import pytest
import respx
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


@respx.mock
def test_stream_end_to_end_replay_and_duckdb_watermark(tmp_path: Path, runner: CliRunner) -> None:
    """End-to-end replay test of baseballpy stream with real GamedayLiveStreamer, watermark diffing and DuckDB upsert."""
    game_pk = 745000
    feed_url = f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
    game_doc = {
        "metaData": {"timeStamp": "20240623_210000"},
        "gameData": {"status": {"abstractGameState": "Final", "detailedState": "Final"}},
        "liveData": {
            "plays": {
                "allPlays": [
                    {
                        "about": {
                            "atBatIndex": 0,
                            "inning": 1,
                            "isTopInning": True,
                            "isComplete": True,
                            "endTime": "2024-06-23T18:05:00Z",
                        },
                        "matchup": {"batter": {"id": 592450}, "pitcher": {"id": 543037}},
                        "result": {"event": "Single", "description": "Judge singles to center."},
                        "count": {"balls": 1, "strikes": 1, "outs": 0},
                        "playEvents": [
                            {
                                "index": 0,
                                "isPitch": True,
                                "startTime": "2024-06-23T18:01:00Z",
                                "details": {"type": {"code": "FF"}, "description": "Called Strike"},
                                "pitchData": {"startSpeed": 97.5},
                                "count": {"balls": 0, "strikes": 1, "outs": 0},
                            },
                            {
                                "index": 1,
                                "isPitch": True,
                                "startTime": "2024-06-23T18:02:00Z",
                                "details": {"type": {"code": "CH"}, "description": "Ball"},
                                "pitchData": {"startSpeed": 88.2},
                                "count": {"balls": 1, "strikes": 1, "outs": 0},
                            },
                        ],
                    },
                    {
                        "about": {
                            "atBatIndex": 1,
                            "inning": 1,
                            "isTopInning": True,
                            "isComplete": True,
                            "endTime": "2024-06-23T18:10:00Z",
                        },
                        "matchup": {"batter": {"id": 660271}, "pitcher": {"id": 543037}},
                        "result": {
                            "event": "Strikeout",
                            "description": "Ohtani strikes out swinging.",
                        },
                        "count": {"balls": 0, "strikes": 3, "outs": 1},
                        "playEvents": [
                            {
                                "index": 0,
                                "isPitch": True,
                                "startTime": "2024-06-23T18:06:00Z",
                                "details": {
                                    "type": {"code": "SL"},
                                    "description": "Swinging Strike",
                                },
                                "pitchData": {"startSpeed": 85.0},
                                "count": {"balls": 0, "strikes": 1, "outs": 0},
                            },
                        ],
                    },
                ]
            }
        },
    }
    route = respx.get(feed_url).mock(return_value=httpx.Response(200, json=game_doc))
    duckdb_file = tmp_path / "stream_e2e.duckdb"

    # 1. First run: stream live events into DuckDB without replay
    res1 = runner.invoke(main, ["stream", str(game_pk), "--duckdb", str(duckdb_file)])
    assert res1.exit_code == 0, res1.output
    assert route.call_count == 1
    assert "events seen" in res1.output

    # Check duckdb count after first run
    con = duckdb.connect(str(duckdb_file))
    try:
        first_count = con.execute("SELECT count(*) FROM live_events").fetchone()[0]
        assert first_count > 0
        unique_pks = con.execute(
            "SELECT count(DISTINCT (game_pk, at_bat_index, event_index)) FROM live_events"
        ).fetchone()[0]
        assert unique_pks == first_count
    finally:
        con.close()

    # 2. Second run without --replay: watermark prevents re-emitting
    res2 = runner.invoke(main, ["stream", str(game_pk), "--duckdb", str(duckdb_file)])
    assert res2.exit_code == 0, res2.output
    assert "0 events seen, 0 events written" in res2.output

    con = duckdb.connect(str(duckdb_file))
    try:
        assert con.execute("SELECT count(*) FROM live_events").fetchone()[0] == first_count
    finally:
        con.close()

    # 3. Third run with --replay: ignores watermark, replays all events, upserts idempotently
    res3 = runner.invoke(main, ["stream", str(game_pk), "--duckdb", str(duckdb_file), "--replay"])
    assert res3.exit_code == 0, res3.output
    assert f"{first_count} events seen, {first_count} events written" in res3.output

    con = duckdb.connect(str(duckdb_file))
    try:
        replay_count = con.execute("SELECT count(*) FROM live_events").fetchone()[0]
        assert replay_count == first_count, "idempotent upsert preserves exact event count"
        unique_pks = con.execute(
            "SELECT count(DISTINCT (game_pk, at_bat_index, event_index)) FROM live_events"
        ).fetchone()[0]
        assert unique_pks == first_count

        # Verify typed attributes
        judge_pitch = con.execute(
            "SELECT pitch_type, start_speed, description FROM live_events WHERE at_bat_index = 0 AND event_index = 0"
        ).fetchone()
        assert judge_pitch == ("FF", 97.5, "Called Strike")
    finally:
        con.close()
