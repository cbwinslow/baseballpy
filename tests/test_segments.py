"""Processed segments (ADR 95, 96): one Parquet file per dataset per segment, counted only by a commit line.

Written first (task 3.1, B-360). Task 3.2 (B-361) built the open files (``ProcessedSegmentFiles``) and
task 3.3 (B-362) the commit, start-up clean-up and journal replay. The tests of ``refresh`` (task 3.4)
and of the writer lock (task 3.5) are expected failures until those tasks; remove their ``xfail`` marks
then (a strict ``xfail`` that passes fails the run).

The interface these tests fix (it extends ``ResponseLog`` of tasks 2.x):

* ``DatasetRows(table, raw_sha256)``: the rows one dataset got from one response, and that response's sha256.
* ``normalize(unit_id, responses) -> {dataset: DatasetRows}``: the source's own parser, the only
  source-specific part. The writer calls it for every new unit and again for every unit it replays.
* ``SegmentWriter(config, source, season, normalize, *, row_group_units=50)``: takes the writer lock of the
  source and season (``core/hostlock.py``), replays the journal, finishes an unfinished refresh.
* ``writer.add_unit(unit_id, responses)``, ``writer.stored()``, ``writer.committed_units()``.
* ``writer.commit()``: rename every file of the segment into place, then append the commit line.
* ``writer.refresh(segment, units)``: rewrite a committed segment under the same file names.

The two points where a run can die are module functions the tests replace: ``_append_commit_line``
(after the renames, before the line) and ``_replace`` (one rename of a ``.part`` file into place).

A commit line carries ``segment``, ``units``, ``raw`` and, per dataset, ``datasets[<dataset>]`` with
``file``, ``rows``, ``sha256`` and ``schema_sha256``.
"""

import json
import subprocess
import sys
from collections.abc import Callable, Generator, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.hostlock import HostBusyError, release_all
from baseballpy.core.responselog import Response

NOT_BUILT = pytest.mark.xfail(
    strict=True,
    raises=(ImportError, NotImplementedError),
    reason="B-363: SegmentWriter.refresh is not built yet",
)

LOCK_NOT_BUILT = pytest.mark.xfail(
    strict=True,
    raises=(ImportError, NotImplementedError, pytest.fail.Exception),
    reason="B-364: the writer lock is not built yet (the second writer is not refused)",
)

FETCHED_AT = "2026-11-08T12:00:00+00:00"
SOURCE = "mlb_api"
SEASON = 2024
PLAYS_PER_GAME = 3


@pytest.fixture(autouse=True)
def _free_locks() -> Generator[None, None, None]:
    """A writer holds its season's lock until the process ends; tests give it back."""
    yield
    release_all()


def _api() -> tuple[Any, Any]:
    """The classes under test, imported late so a missing module fails the test, not the collection."""
    from baseballpy.core.segments import DatasetRows, SegmentWriter  # type: ignore[import-not-found]

    return DatasetRows, SegmentWriter


def _responses(game: str, plays: int = PLAYS_PER_GAME) -> list[Response]:
    feed = json.dumps({"game": game, "plays": plays, "pad": "x" * 2000}).encode()
    box = json.dumps({"game": game, "runs": 4}).encode()
    return [
        Response(f"https://statsapi.mlb.com/api/v1.1/game/{game}/feed/live", feed, FETCHED_AT),
        Response(f"https://statsapi.mlb.com/api/v1/game/{game}/boxscore", box, FETCHED_AT),
    ]


def _normalize(rows_class: Any) -> Callable[[str, Sequence[Response]], dict[str, Any]]:
    """Three datasets: ``plays`` (from the feed), ``box`` (from the boxscore), ``empty`` (never any row)."""

    def normalize(unit_id: str, responses: Sequence[Response]) -> dict[str, Any]:
        feed, box = responses
        plays = json.loads(feed.body)["plays"]
        return {
            "plays": rows_class(
                pa.table({"game_id": [unit_id] * plays, "seq": list(range(plays))}), feed.sha256
            ),
            "box": rows_class(pa.table({"game_id": [unit_id], "runs": [4]}), box.sha256),
            "empty": rows_class(pa.table({"game_id": pa.array([], pa.string())}), feed.sha256),
        }

    return normalize


def _writer(tmp_path: Path, **options: Any) -> Any:
    rows_class, writer_class = _api()
    return writer_class(
        LakeConfig(home=tmp_path), SOURCE, SEASON, _normalize(rows_class), **options
    )


def _games(count: int) -> list[str]:
    return [str(745000 + n) for n in range(count)]


def _add(writer: Any, games: list[str], plays: int = PLAYS_PER_GAME) -> None:
    for game in games:
        writer.add_unit(game, _responses(game, plays))


def _season_dir(config: LakeConfig, dataset: str) -> Path:
    return config.processed_dir(SOURCE, dataset, SEASON)


def _raw_dir(config: LakeConfig) -> Path:
    return config.raw_root / SOURCE / f"season={SEASON}"


def _lines(config: LakeConfig) -> list[dict[str, Any]]:
    path = _raw_dir(config) / "segments.json"
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _files(config: LakeConfig, dataset: str) -> list[Path]:
    folder = _season_dir(config, dataset)
    return sorted(folder.glob("seg-*.parquet")) if folder.is_dir() else []


def _rows(config: LakeConfig, dataset: str) -> list[dict[str, Any]]:
    return [row for path in _files(config, dataset) for row in pq.read_table(path).to_pylist()]


def test_a_segment_writes_one_file_per_dataset_in_bounded_row_groups(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    writer = _writer(tmp_path, row_group_units=50)
    _add(writer, _games(120))
    assert writer.commit() == 1

    assert [p.name for p in _files(config, "plays")] == ["seg-0001.parquet"]
    assert [p.name for p in _files(config, "box")] == ["seg-0001.parquet"]
    assert _files(config, "empty") == [], "a dataset with no row in the segment gets no file"
    plays = pq.ParquetFile(_files(config, "plays")[0])
    assert plays.metadata.num_row_groups == 3
    assert [plays.metadata.row_group(i).num_rows for i in range(3)] == [150, 150, 60]
    assert pq.ParquetFile(_files(config, "box")[0]).metadata.num_row_groups == 3
    assert len(list((_raw_dir(config)).glob("seg-*.parquet"))) == 1, "one raw segment"
    assert not list(tmp_path.rglob("*.part")), "no .part file is left anywhere"
    line = _lines(config)[0]
    assert line["datasets"]["plays"]["rows"] == 360 and line["datasets"]["empty"]["rows"] == 0


def test_every_processed_row_names_its_response(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    writer = _writer(tmp_path)
    _add(writer, _games(4))
    writer.commit()

    raw = pq.read_table(next(_raw_dir(config).glob("seg-*.parquet"))).to_pylist()
    by_sha = {row["sha256"]: row["url"] for row in raw}
    for row in _rows(config, "plays"):
        assert by_sha[row["_raw_sha256"]].endswith(f"/game/{row['game_id']}/feed/live")
    for row in _rows(config, "box"):
        assert by_sha[row["_raw_sha256"]].endswith(f"/game/{row['game_id']}/boxscore")


def test_a_game_counts_only_after_its_commit_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = LakeConfig(home=tmp_path)
    writer = _writer(tmp_path)
    _add(writer, _games(3))
    assert writer.committed_units() == frozenset()

    def die(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("the run died before the commit line")

    monkeypatch.setattr("baseballpy.core.segments._append_commit_line", die)
    with pytest.raises(RuntimeError, match="died"):
        writer.commit()
    assert _lines(config) == []
    release_all()
    monkeypatch.undo()

    again = _writer(tmp_path)
    assert again.committed_units() == frozenset(), "no line, so no game is counted"
    assert again.stored() == frozenset(_games(3)), "but the journal still holds them"
    assert again.commit() == 1
    assert again.committed_units() == frozenset(_games(3))


def test_start_up_deletes_uncommitted_files_and_replays_the_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = LakeConfig(home=tmp_path)
    writer = _writer(tmp_path)
    _add(writer, _games(3))

    def die(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("the run died before the commit line")

    monkeypatch.setattr("baseballpy.core.segments._append_commit_line", die)
    with pytest.raises(RuntimeError):
        writer.commit()
    assert _files(config, "plays"), "the renamed files are on disk, but no line names them"
    release_all()
    monkeypatch.undo()

    again = _writer(tmp_path)
    assert _files(config, "plays") == [] and _files(config, "box") == []
    assert not list((_raw_dir(config)).glob("seg-*.parquet"))
    assert not list(tmp_path.rglob("*.part"))
    assert again.stored() == frozenset(_games(3)), "the journal is replayed"
    again.commit()
    assert len(_rows(config, "plays")) == 9 and len(_rows(config, "box")) == 3, "every game once"


def test_a_torn_commit_line_is_ignored(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    first = _writer(tmp_path)
    _add(first, _games(2))
    assert first.commit() == 1
    release_all()
    with (_raw_dir(config) / "segments.json").open("ab") as handle:
        handle.write(b'{"segment":2,"units":["7450')  # cut short by a crash

    second = _writer(tmp_path)
    assert second.committed_units() == frozenset(_games(2))
    _add(second, _games(4)[2:])
    assert second.commit() == 2
    assert [line["segment"] for line in _lines(config)] == [1, 2]
    assert len(_rows(config, "box")) == 4


@LOCK_NOT_BUILT
def test_a_second_writer_on_the_same_season_is_refused(tmp_path: Path) -> None:
    _api()  # a missing module fails here, before a child process is started
    holder_code = (
        "import sys\n"
        "from pathlib import Path\n"
        "from baseballpy.core.config import LakeConfig\n"
        "from baseballpy.core.segments import SegmentWriter\n"
        "SegmentWriter(LakeConfig(home=Path(sys.argv[1])), 'mlb_api', 2024, lambda u, r: {})\n"
        "print('held', flush=True)\n"
        "sys.stdin.readline()\n"
    )
    holder = subprocess.Popen(  # noqa: S603 - runs this interpreter on a fixed script
        [sys.executable, "-c", holder_code, str(tmp_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None and holder.stdout.readline().strip() == "held"
        before = sorted(tmp_path.rglob("*"))
        with pytest.raises(HostBusyError, match="mlb_api"):
            _writer(tmp_path)
        assert sorted(tmp_path.rglob("*")) == before, "the first writer's files are untouched"
    finally:
        assert holder.stdin is not None
        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=30)


@NOT_BUILT
def test_a_refresh_replaces_a_segment_under_the_same_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = LakeConfig(home=tmp_path)
    writer = _writer(tmp_path)
    games = _games(2)
    _add(writer, games)
    assert writer.commit() == 1
    old_plays = _files(config, "plays")[0].read_bytes()

    # a corrected feed: five plays per game instead of three
    corrected = {game: _responses(game, plays=5) for game in games}
    writer.refresh(1, corrected)
    assert [p.name for p in _files(config, "plays")] == ["seg-0001.parquet"], "one file, same name"
    assert [p.name for p in _files(config, "box")] == ["seg-0001.parquet"]
    assert _files(config, "plays")[0].read_bytes() != old_plays
    assert len(_rows(config, "plays")) == 10 and len(_rows(config, "box")) == 2

    # a second refresh is stopped after one of its renames: a reader never sees both versions
    import baseballpy.core.segments as segments_module

    real_replace = segments_module._replace
    calls = {"n": 0}

    def replace_once_then_die(source: Path, target: Path) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("the run died between two renames")
        real_replace(source, target)

    monkeypatch.setattr(segments_module, "_replace", replace_once_then_die)
    again = {game: _responses(game, plays=7) for game in games}
    with pytest.raises(RuntimeError, match="between two renames"):
        writer.refresh(1, again)
    for dataset in ("plays", "box"):
        assert [p.name for p in _files(config, dataset)] == ["seg-0001.parquet"]
    assert len(_rows(config, "plays")) in (10, 14), "old or new rows of the segment, never both"
    release_all()
    monkeypatch.undo()

    restarted = _writer(tmp_path)  # the next start finishes the stopped refresh
    assert len(_rows(config, "plays")) == 14 and len(_rows(config, "box")) == 2
    assert restarted.committed_units() == frozenset(games)


def test_a_journal_left_after_its_commit_line_is_not_committed_twice(tmp_path: Path) -> None:
    """The run died after the line was written but before the journal was deleted."""
    config = LakeConfig(home=tmp_path)
    writer = _writer(tmp_path)
    _add(writer, _games(2))
    journal = (_raw_dir(config) / "_open" / "journal.zst").read_bytes()
    assert writer.commit() == 1
    release_all()
    (_raw_dir(config) / "_open").mkdir(exist_ok=True)
    (_raw_dir(config) / "_open" / "journal.zst").write_bytes(journal)

    again = _writer(tmp_path)
    assert again.committed_units() == frozenset(_games(2))
    assert again.commit() is None, "nothing is open: the leftover journal held only committed games"
    assert not (_raw_dir(config) / "_open" / "journal.zst").exists()
    assert len(_rows(config, "box")) == 2 and [line["segment"] for line in _lines(config)] == [1]


def test_committing_nothing_writes_nothing(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    assert _writer(tmp_path).commit() is None
    assert _lines(config) == [] and not list(tmp_path.rglob("*.parquet"))
