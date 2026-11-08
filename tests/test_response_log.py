"""The response log (ADR 95): each HTTP response is stored once, a crash loses no finished game.

Written first (task 2.1, B-356); the journal came with task 2.2 (B-357) and the raw segment writer
with task 2.3 (B-358), which made these tests pass.

The interface these tests fix:

* ``Response(url, body, fetched_at, status=200, etag="")``: one HTTP response, the original bytes.
* ``ResponseLog(config, source, season)``: the log of one source and season.
* ``log.stored()``: the unit ids (a unit is one game) that are journalled or committed.
* ``log.add_unit(unit_id, responses)``: journal every response of a unit, flushed before it returns.
* ``log.commit()``: write the raw segment and its line in ``segments.json``, then delete the journal.
* ``log.read(sha256)``: the original bytes of a stored response.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from baseballpy.core.config import LakeConfig

FETCHED_AT = "2026-11-08T12:00:00+00:00"
SOURCE = "mlb_api"
SEASON = 2024


def _api() -> tuple[Any, Any]:
    """The classes under test, imported late so a missing module fails the test, not the collection."""
    from baseballpy.core.responselog import Response, ResponseLog  # type: ignore[import-not-found]

    return Response, ResponseLog


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _body(label: str) -> bytes:
    """A JSON-looking body that is different for every label and compresses well."""
    return (
        b'{"label": "'
        + label.encode()
        + b'", "rows": ['
        + b'{"id": 1, "name": "x"},' * 50
        + b"{}]}"
    )


def _unit_responses(response_class: Any, game: str) -> list[Any]:
    """The responses of one game: two URLs here (the real source has five)."""
    return [
        response_class(
            url=f"https://statsapi.mlb.com/api/v1.1/game/{game}/feed/live",
            body=_body(f"feed-{game}"),
            fetched_at=FETCHED_AT,
        ),
        response_class(
            url=f"https://statsapi.mlb.com/api/v1/game/{game}/boxscore",
            body=_body(f"box-{game}"),
            fetched_at=FETCHED_AT,
        ),
    ]


def _season_dir(config: LakeConfig) -> Path:
    return config.raw_root / SOURCE / f"season={SEASON}"


def _commit_lines(config: LakeConfig) -> list[dict[str, Any]]:
    text = (_season_dir(config) / "segments.json").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _run(log: Any, response_class: Any, games: list[str], fetched: list[str]) -> None:
    """What a downloader does: skip the games the log already holds, fetch and add the rest."""
    for game in games:
        if game in log.stored():
            continue
        fetched.append(game)
        log.add_unit(game, _unit_responses(response_class, game))


def test_each_response_is_stored_once_with_the_sha256_of_its_original_bytes(tmp_path: Path) -> None:
    response_class, log_class = _api()
    config = LakeConfig(home=tmp_path)
    log = log_class(config, SOURCE, SEASON)
    for game in ("745001", "745002", "745003"):
        log.add_unit(game, _unit_responses(response_class, game))
    log.commit()

    files = sorted(_season_dir(config).glob("seg-*.parquet"))
    assert len(files) == 1
    table = pq.read_table(files[0])
    assert {"url", "fetched_at", "status", "etag", "sha256", "body"} <= set(table.column_names)
    rows = table.to_pylist()
    assert len(rows) == 6  # three games, two URLs each, one row per response
    assert len({row["url"] for row in rows}) == 6
    for row in rows:
        assert row["sha256"] == _sha(row["body"]), "the sha256 is that of the original bytes"
        assert row["status"] == 200 and row["fetched_at"] == FETCHED_AT
    for game in ("745001", "745002", "745003"):
        for label in (f"feed-{game}", f"box-{game}"):
            assert log.read(_sha(_body(label))) == _body(label)


def test_a_crash_replays_the_journal_and_refetches_no_finished_game(tmp_path: Path) -> None:
    response_class, log_class = _api()
    config = LakeConfig(home=tmp_path)
    games = ["745001", "745002", "745003"]

    first = log_class(config, SOURCE, SEASON)
    fetched_first: list[str] = []
    _run(first, response_class, games[:2], fetched_first)
    assert fetched_first == games[:2]
    del first  # the run is killed here: nothing was committed, only the journal exists
    assert (_season_dir(config) / "_open" / "journal.zst").exists()
    assert not list(_season_dir(config).glob("seg-*.parquet"))

    second = log_class(config, SOURCE, SEASON)
    assert second.stored() == frozenset(games[:2]), "the journal is replayed on start"
    fetched_second: list[str] = []
    _run(second, response_class, games, fetched_second)
    assert fetched_second == ["745003"], "no finished game is fetched again"
    second.commit()

    lines = _commit_lines(config)
    assert len(lines) == 1 and sorted(lines[0]["units"]) == games
    rows = pq.read_table(next(_season_dir(config).glob("seg-*.parquet"))).to_pylist()
    assert len(rows) == 6 and len({row["sha256"] for row in rows}) == 6, "every response once"
    assert not (_season_dir(config) / "_open" / "journal.zst").exists(), "deleted after the commit"


def test_a_torn_last_journal_record_is_dropped(tmp_path: Path) -> None:
    response_class, log_class = _api()
    config = LakeConfig(home=tmp_path)
    first = log_class(config, SOURCE, SEASON)
    for game in ("745001", "745002"):
        first.add_unit(game, _unit_responses(response_class, game))
    del first
    journal = _season_dir(config) / "_open" / "journal.zst"
    data = journal.read_bytes()
    journal.write_bytes(data[:-5])  # the power went out in the middle of the last record

    second = log_class(config, SOURCE, SEASON)
    assert second.stored() == frozenset({"745001"}), (
        "whole records are kept, the torn one is dropped"
    )
    fetched: list[str] = []
    _run(second, response_class, ["745001", "745002"], fetched)
    assert fetched == ["745002"], "the game of the torn record is fetched again"
    second.commit()
    lines = _commit_lines(config)
    assert len(lines) == 1 and sorted(lines[0]["units"]) == ["745001", "745002"]


def test_a_source_on_segments_writes_no_per_dataset_or_gzip_raw_file(tmp_path: Path) -> None:
    response_class, log_class = _api()
    config = LakeConfig(home=tmp_path)
    log = log_class(config, SOURCE, SEASON)
    for game in ("745001", "745002"):
        log.add_unit(game, _unit_responses(response_class, game))
    log.commit()

    source_dir = config.raw_root / SOURCE
    names = sorted(
        path.relative_to(source_dir).as_posix() for path in source_dir.rglob("*") if path.is_file()
    )
    assert len(names) == 2, names
    assert re.fullmatch(r"season=2024/seg-\d{4}\.parquet", names[0]), names
    assert names[1] == "season=2024/segments.json", names
    assert not list(source_dir.rglob("*.gz")), "no gzip raw file"
    assert not list(source_dir.rglob("_manifest.json")), "no per-dataset raw manifest"
    assert {path.name for path in source_dir.iterdir()} == {"season=2024"}, "no per-dataset folder"


def test_a_segment_file_no_line_names_is_deleted_and_its_games_come_back_from_the_journal(
    tmp_path: Path,
) -> None:
    response_class, log_class = _api()
    config = LakeConfig(home=tmp_path)
    log = log_class(config, SOURCE, SEASON)
    log.add_unit("745001", _unit_responses(response_class, "745001"))
    journal = (_season_dir(config) / "_open" / "journal.zst").read_bytes()
    log.commit()
    # the run died after the rename, before the line: put the state back as that crash leaves it
    (_season_dir(config) / "segments.json").unlink()
    (_season_dir(config) / "_open").mkdir(exist_ok=True)
    (_season_dir(config) / "_open" / "journal.zst").write_bytes(journal)

    again = log_class(config, SOURCE, SEASON)
    assert not list(_season_dir(config).glob("seg-*.parquet")), "the unnamed segment is deleted"
    assert again.stored() == frozenset({"745001"}), "the game is back from the journal"
    again.commit()
    assert len(_commit_lines(config)) == 1


def test_a_torn_commit_line_is_ignored_and_the_next_segment_is_numbered_after_the_last(
    tmp_path: Path,
) -> None:
    response_class, log_class = _api()
    config = LakeConfig(home=tmp_path)
    first = log_class(config, SOURCE, SEASON)
    first.add_unit("745001", _unit_responses(response_class, "745001"))
    assert first.commit() == 1
    with (_season_dir(config) / "segments.json").open("ab") as handle:
        handle.write(b'{"segment":2,"units":["7450')  # a line cut short by a crash

    second = log_class(config, SOURCE, SEASON)
    assert second.stored() == frozenset({"745001"})
    second.add_unit("745002", _unit_responses(response_class, "745002"))
    assert second.commit() == 2
    assert [line["segment"] for line in _commit_lines(config)] == [1, 2]
    assert sorted(p.name for p in _season_dir(config).glob("seg-*.parquet")) == [
        "seg-0001.parquet",
        "seg-0002.parquet",
    ]
    # a response is read back from a committed segment by a fresh log
    reopened = log_class(config, SOURCE, SEASON)
    assert reopened.read(_sha(_body("box-745001"))) == _body("box-745001")
    assert reopened.read(_sha(_body("feed-745002"))) == _body("feed-745002")


def test_committing_nothing_writes_nothing_and_an_unknown_hash_is_an_error(tmp_path: Path) -> None:
    _, log_class = _api()
    config = LakeConfig(home=tmp_path)
    log = log_class(config, SOURCE, SEASON)
    assert log.commit() is None
    assert not (tmp_path / "raw").exists()
    with pytest.raises(KeyError):
        log.read("0" * 64)


def test_the_raw_segment_sink_is_a_sink_protocol(tmp_path: Path) -> None:
    from baseballpy.core.protocols import SinkProtocol
    from baseballpy.core.responselog import RAW_SCHEMA, RawSegmentSink

    sink: SinkProtocol = RawSegmentSink()
    empty = RAW_SCHEMA.empty_table()
    assert sink.write(empty, str(tmp_path / "seg-0001.parquet")) == 0
    assert not list(tmp_path.glob("*.part"))


def test_the_responses_of_one_game_stay_next_to_each_other(tmp_path: Path) -> None:
    """Measured (design section 3): sorted by kind a segment is 2.5 times larger than grouped by game."""
    response_class, log_class = _api()
    config = LakeConfig(home=tmp_path)
    log = log_class(config, SOURCE, SEASON)
    games = ["745001", "745002", "745003"]
    for game in games:
        log.add_unit(game, _unit_responses(response_class, game))
    log.commit()
    rows = pq.read_table(next(_season_dir(config).glob("seg-*.parquet"))).to_pylist()
    order = [row["url"].split("/game/")[1].split("/")[0] for row in rows]
    assert order == [game for game in games for _ in range(2)]
