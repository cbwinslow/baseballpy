"""The response log (ADR 95): each HTTP response is stored once, a crash loses no finished game.

Written first (task 2.1, B-356). ``baseballpy.core.responselog`` does not exist yet: task 2.2 (B-357)
builds the journal and task 2.3 (B-358) the raw segment writer. Until then every test is an expected
failure that must fail because the module is missing (``ImportError``), not for another reason.
Remove the ``xfail`` marks when the tests start to pass; a strict ``xfail`` that passes fails the run,
so nobody can forget.

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

NOT_BUILT = pytest.mark.xfail(
    strict=True,
    raises=ImportError,
    reason="B-357/B-358: baseballpy.core.responselog is not built yet",
)

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


@NOT_BUILT
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


@NOT_BUILT
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


@NOT_BUILT
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


@NOT_BUILT
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
