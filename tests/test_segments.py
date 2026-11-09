"""Processed segments (ADR 95, 96): one Parquet file per dataset per segment, counted only by a commit line.

Written first (task 3.1, B-360); tasks 3.2 to 3.5 (B-361 to B-364) built the open files, the commit,
the refresh and the writer lock, and made these tests pass.

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
        with pytest.raises(HostBusyError, match="mlb_api season 2024"):
            _writer(tmp_path)
        assert sorted(tmp_path.rglob("*")) == before, "the first writer's files are untouched"
        _, writer_class = _api()  # another season of the same source is not blocked
        writer_class(LakeConfig(home=tmp_path), "mlb_api", 2023, lambda u, r: {})
    finally:
        assert holder.stdin is not None
        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=30)


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


def test_a_refresh_keeps_every_old_raw_row_and_adds_the_new_responses(tmp_path: Path) -> None:
    """Raw is never overwritten: a refetch with different bytes is a new row (design 5b)."""
    config = LakeConfig(home=tmp_path)
    writer = _writer(tmp_path)
    games = _games(2)
    _add(writer, games)
    writer.commit()
    raw_file = next(_raw_dir(config).glob("seg-*.parquet"))
    before = pq.read_table(raw_file).to_pylist()

    writer.refresh(1, {game: _responses(game, plays=5) for game in games})
    after = pq.read_table(raw_file).to_pylist()
    assert len(before) == 4 and len(after) == 6, (
        "the two corrected feeds are added, the boxscores are the same"
    )
    assert {row["sha256"] for row in before} <= {row["sha256"] for row in after}
    lines = _lines(config)
    assert [line["segment"] for line in lines] == [1, 1] and lines[1]["refresh"] == 1
    assert lines[1]["files"][raw_file.name]["rows"] == 6
    # the newest processed rows name raw rows that exist
    shas = {row["sha256"] for row in after}
    assert {row["_raw_sha256"] for row in _rows(config, "plays")} <= shas


def test_a_refresh_must_name_exactly_the_units_of_a_committed_segment(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    _add(writer, _games(2))
    writer.commit()
    with pytest.raises(ValueError, match="not committed"):
        writer.refresh(9, {})
    with pytest.raises(ValueError, match="exactly its units"):
        writer.refresh(1, {"745000": _responses("745000")})


def test_a_refresh_journal_whose_line_is_already_written_is_not_run_twice(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    writer = _writer(tmp_path)
    games = _games(2)
    _add(writer, games)
    writer.commit()
    writer.refresh(1, {game: _responses(game, plays=5) for game in games})
    journal = _raw_dir(config) / "_open" / "refresh-0001.zst"
    assert not journal.exists(), "deleted when the refresh is done"
    # the run died after the line, before the journal was deleted: put the journal back
    from baseballpy.core.responselog import encode_record

    journal.parent.mkdir(exist_ok=True)
    journal.write_bytes(b"".join(encode_record(g, _responses(g, plays=5)) for g in games))
    release_all()
    # the journal is the very one the line names (same refresh id), so nothing runs again
    _writer(tmp_path)
    assert len(_rows(config, "plays")) == 10 and len(_rows(config, "box")) == 2
    assert not journal.exists()
    assert [line["segment"] for line in _lines(config)] == [1, 1], "no third line"


def test_a_refresh_with_no_rows_for_a_dataset_removes_its_old_file(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    writer = _writer(tmp_path)
    games = _games(2)
    _add(writer, games)
    writer.commit()
    assert _files(config, "plays")
    writer.refresh(1, {game: _responses(game, plays=0) for game in games})
    assert _files(config, "plays") == [] and len(_rows(config, "box")) == 2
    assert _lines(config)[-1]["datasets"]["plays"] == {"file": None, "rows": 0}


def _committed_lake(tmp_path: Path) -> LakeConfig:
    config = LakeConfig(home=tmp_path)
    writer = _writer(tmp_path)
    _add(writer, _games(3))
    writer.commit()
    release_all()
    return config


def _verdicts(config: LakeConfig) -> dict[tuple[str, str], str]:
    from baseballpy.cache_check import check_segments

    return {(r.dataset, r.name): r.integrity for r in check_segments(config)}


def _cache_check_exit(tmp_path: Path) -> tuple[int, str]:
    from click.testing import CliRunner

    from baseballpy.cli import main

    result = CliRunner().invoke(
        main, ["cache", "check", "--source", SOURCE], env={"BASEBALLPY_HOME": str(tmp_path)}
    )
    return result.exit_code, result.output


def test_cache_check_finds_a_damaged_segment(tmp_path: Path) -> None:
    config = _committed_lake(tmp_path)
    assert _verdicts(config) == {
        ("(raw segments)", "seg-0001.parquet"): "ok",
        ("plays", "seg-0001.parquet"): "ok",
        ("box", "seg-0001.parquet"): "ok",
    }
    assert _cache_check_exit(tmp_path)[0] == 0, "a clean lake exits 0"

    raw_file = next(_raw_dir(config).glob("seg-*.parquet"))
    data = bytearray(raw_file.read_bytes())
    data[len(data) // 2] ^= 0xFF  # one byte changed on disk after the commit
    raw_file.write_bytes(bytes(data))
    _files(config, "box")[0].unlink()
    plays = _files(config, "plays")[0]
    plays.write_bytes(plays.read_bytes()[:-20])  # cut short

    verdicts = _verdicts(config)
    assert verdicts[("(raw segments)", "seg-0001.parquet")] == "corrupt"
    assert verdicts[("box", "seg-0001.parquet")] == "missing"
    assert verdicts[("plays", "seg-0001.parquet")] == "corrupt"
    code, output = _cache_check_exit(tmp_path)
    assert code == 1 and "seg-0001.parquet" in output


def test_cache_check_finds_a_raw_row_whose_bytes_do_not_match_its_hash(tmp_path: Path) -> None:
    from baseballpy.core.responselog import file_sha256

    config = _committed_lake(tmp_path)
    raw_file = next(_raw_dir(config).glob("seg-*.parquet"))
    table = pq.read_table(raw_file)
    bodies = table.column("body").to_pylist()
    bodies[0] = bodies[0] + b" "  # a body that no longer matches its row's sha256
    pq.write_table(table.set_column(5, "body", pa.array(bodies, pa.large_binary())), raw_file)
    # the file is now consistent with a recomputed file hash, so only the row check can see it
    path = _raw_dir(config) / "segments.json"
    line = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    line["files"][raw_file.name]["sha256"] = file_sha256(raw_file)
    path.write_text(json.dumps(line, separators=(",", ":")) + "\n", encoding="utf-8")

    assert _verdicts(config)[("(raw segments)", "seg-0001.parquet")] == "corrupt"
