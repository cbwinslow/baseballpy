"""The journal of the response log: whole records survive, a torn or damaged tail is dropped."""

from pathlib import Path

from baseballpy.core.config import LakeConfig
from baseballpy.core.responselog import (
    Response,
    ResponseLog,
    encode_record,
    pack_unit,
    read_journal,
    unpack_unit,
)

FETCHED_AT = "2026-11-08T12:00:00+00:00"


def _responses(game: str) -> list[Response]:
    body = (
        b'{"game": "' + game.encode() + b'", "rows": [' + b'{"id": 1, "name": "x"},' * 200 + b"{}]}"
    )
    return [
        Response(f"https://statsapi.mlb.com/api/v1.1/game/{game}/feed/live", body, FETCHED_AT),
        Response(
            f"https://statsapi.mlb.com/api/v1/game/{game}/boxscore",
            b"\x00\xff binary \xc3\xa9",
            FETCHED_AT,
            status=200,
            etag='W/"abc"',
        ),
    ]


def _log(tmp_path: Path, season: int | None = 2024) -> ResponseLog:
    return ResponseLog(LakeConfig(home=tmp_path), "mlb_api", season)


def test_a_unit_packs_and_unpacks_to_the_same_responses() -> None:
    responses = _responses("745001")
    assert unpack_unit(pack_unit("745001", responses)) == ("745001", responses)


def test_asking_for_a_log_creates_nothing_and_adding_a_unit_creates_the_open_folder(
    tmp_path: Path,
) -> None:
    log = _log(tmp_path)
    assert not (tmp_path / "raw").exists() and log.stored() == frozenset()
    log.add_unit("745001", _responses("745001"))
    assert (
        log.journal_path == tmp_path / "raw" / "mlb_api" / "season=2024" / "_open" / "journal.zst"
    )
    assert log.journal_path.exists()


def test_a_source_without_seasons_has_no_season_folder(tmp_path: Path) -> None:
    log = _log(tmp_path, season=None)
    log.add_unit("a", _responses("1"))
    assert log.journal_path == tmp_path / "raw" / "mlb_api" / "_open" / "journal.zst"


def test_the_journal_is_compressed_and_replays_every_unit_byte_for_byte(tmp_path: Path) -> None:
    log = _log(tmp_path)
    for game in ("745001", "745002", "745003"):
        log.add_unit(game, _responses(game))
    original = sum(len(r.body) for g in ("745001", "745002", "745003") for r in _responses(g))
    assert log.journal_path.stat().st_size < original / 5
    again = _log(tmp_path)
    assert again.stored() == frozenset({"745001", "745002", "745003"})
    units, good = read_journal(log.journal_path)
    assert good == log.journal_path.stat().st_size
    assert units["745002"] == _responses("745002")


def test_a_torn_tail_is_cut_off_so_new_records_follow_whole_ones(tmp_path: Path) -> None:
    log = _log(tmp_path)
    log.add_unit("745001", _responses("745001"))
    log.add_unit("745002", _responses("745002"))
    whole = len(encode_record("745001", _responses("745001")))
    for cut in (1, 5, 11, 20):  # in the body and in the header of the last record
        data = log.journal_path.read_bytes()
        log.journal_path.write_bytes(data[: len(data) - cut] if cut < 20 else data[: whole + 3])
        reopened = _log(tmp_path)
        assert reopened.stored() == frozenset({"745001"}), cut
        assert log.journal_path.stat().st_size == whole, "cut back to the last whole record"
        reopened.add_unit("745002", _responses("745002"))
        assert _log(tmp_path).stored() == frozenset({"745001", "745002"})


def test_a_damaged_record_ends_the_replay(tmp_path: Path) -> None:
    log = _log(tmp_path)
    for game in ("745001", "745002", "745003"):
        log.add_unit(game, _responses(game))
    first = len(encode_record("745001", _responses("745001")))
    data = bytearray(log.journal_path.read_bytes())
    data[first + 20] ^= 0xFF  # one flipped byte inside the second record
    log.journal_path.write_bytes(bytes(data))
    assert _log(tmp_path).stored() == frozenset({"745001"})


def test_a_unit_added_twice_keeps_its_last_version(tmp_path: Path) -> None:
    log = _log(tmp_path)
    old = _responses("745001")
    new = [Response(old[0].url, b'{"corrected": true}', "2026-11-09T00:00:00+00:00")]
    log.add_unit("745001", old)
    log.add_unit("745001", new)
    assert _log(tmp_path)._units["745001"] == new  # noqa: SLF001 - the replayed state is the point


def test_the_sha256_is_that_of_the_original_bytes() -> None:
    import hashlib

    response = _responses("745001")[0]
    assert response.sha256 == hashlib.sha256(response.body).hexdigest()
