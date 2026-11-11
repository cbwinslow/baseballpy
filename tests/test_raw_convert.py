"""Converting the old per-dataset raw files into raw segments (ADR 95; tasks 5.1 to 5.3 of response-log-segments).

Written first. The interface these tests fix (``baseballpy.core.rawsegconvert``):

* ``convert_raw_to_segments(config, source, season, *, dry_run=True, remove_old=False)`` reads every old raw
  file of the season (``raw/<source>/<dataset>/season=Y/<name>``, plain or gzipped) with its manifest entry.
  The entry's ``source_ref`` is the URL, ``sha256`` the checksum of the original bytes, ``fetched_at`` and
  ``etag`` the rest. It returns a ``SegmentConvertReport``.
* The report: ``files`` (old files seen), ``urls`` (distinct URLs), ``copies`` (files whose URL and bytes are
  already held by another file), ``distinct_bodies`` (distinct URL and sha256 pairs), ``differing_urls`` (URLs
  with more than one distinct body: all are kept), ``bytes_before``, ``segments`` (names of the raw segments
  committed by this call), ``removed`` (old files removed), ``skipped`` (``{file: why}``) and ``verified``.
* A dry run changes nothing. Every file is checked against the sha256 of its manifest entry first; one that does
  not match (or has no URL) is listed in ``skipped`` and the season writes nothing and removes nothing.
* The raw segment has one row per distinct URL and body (never one per copy): ``url``, ``fetched_at``,
  ``status`` 200, ``etag``, ``sha256``, ``body`` and ``legacy_path`` (the old ``<dataset>/<name>`` of every copy,
  comma separated). One commit line names the units (the URLs).
* Old files go only after the new segment was read back (every row's body hashes to its sha256 and every old
  file's URL and bytes are present) and only with ``remove_old=True``; a failed read-back rolls the new segment
  back and keeps every old file. A rerun writes nothing new.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from baseballpy.core import rawsegconvert
from baseballpy.core.config import LakeConfig
from baseballpy.core.rawsegconvert import convert_raw_to_segments
from baseballpy.core.stores import RawStore

SOURCE = "mlb_api"
SEASON = 2024
FEED = "https://statsapi.mlb.com/api/v1.1/game/745000/feed/live"
BOX = "https://statsapi.mlb.com/api/v1/game/745000/boxscore"
FEED_BODY = b'{"gameData": {"game": {"pk": 745000}}, "liveData": {"plays": []}}'
FEED_BODY_LATER = b'{"gameData": {"game": {"pk": 745000}}, "liveData": {"plays": [], "x": 1}}'
BOX_BODY = b'{"teams": {"home": {}, "away": {}}}'


def _old_season(tmp_path: Path) -> LakeConfig:
    """Four old raw files: two datasets cut from one feed answer, a later feed answer, one box score."""
    config = LakeConfig(home=tmp_path)
    raw = RawStore(config)
    put = lambda dataset, body, url: raw.put(  # noqa: E731
        SOURCE, dataset, f"{dataset}_745000.json", body, season=SEASON, source_ref=url
    )
    put("game_feed_plays", FEED_BODY, FEED)
    put("game_feed_play_events", FEED_BODY, FEED)
    put("game_feed_linescore_innings", FEED_BODY_LATER, FEED)  # fetched later: different bytes
    put("game_boxscore_info", BOX_BODY, BOX)
    return config


def _tree(config: LakeConfig) -> dict[str, int]:
    root = config.raw_root / SOURCE
    return {
        p.relative_to(root).as_posix(): p.stat().st_size
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _segment_rows(config: LakeConfig) -> list[dict[str, Any]]:
    folder = config.raw_root / SOURCE / f"season={SEASON}"
    rows: list[dict[str, Any]] = []
    for path in sorted(folder.glob("seg-*.parquet")):
        rows += pq.read_table(path).to_pylist()
    return rows


def test_the_dry_run_reports_and_changes_nothing(tmp_path: Path) -> None:
    config = _old_season(tmp_path)
    before = _tree(config)
    report = convert_raw_to_segments(config, SOURCE, SEASON)  # dry_run defaults to True
    assert (report.files, report.urls, report.distinct_bodies) == (4, 2, 3)
    assert (report.copies, report.differing_urls) == (1, 1)
    assert report.bytes_before == sum(map(len, (FEED_BODY, FEED_BODY, FEED_BODY_LATER, BOX_BODY)))
    assert report.segments == [] and report.removed == 0
    assert _tree(config) == before


def test_every_sha256_is_checked_against_the_old_manifest(tmp_path: Path) -> None:
    config = _old_season(tmp_path)
    stored = RawStore(config).stored_path(
        SOURCE, "game_boxscore_info", "game_boxscore_info_745000.json", SEASON
    )
    assert stored is not None
    manifest = (
        config.raw_root / SOURCE / "game_boxscore_info" / f"season={SEASON}" / "_manifest.json"
    )
    entry = next(iter(json.loads(manifest.read_text(encoding="utf-8"))["chunks"].values()))
    assert entry["sha256"] == hashlib.sha256(BOX_BODY).hexdigest()
    RawStore(config).put(
        SOURCE,
        "game_boxscore_info",
        "game_boxscore_info_745000.json",
        BOX_BODY,
        season=SEASON,
        source_ref=BOX,
    )
    # the stored bytes change behind the manifest's back
    stored = RawStore(config).stored_path(
        SOURCE, "game_boxscore_info", "game_boxscore_info_745000.json", SEASON
    )
    assert stored is not None
    stored.write_bytes(stored.read_bytes()[:-4] + b"torn")
    before = _tree(config)
    report = convert_raw_to_segments(config, SOURCE, SEASON, dry_run=False, remove_old=True)
    assert len(report.skipped) == 1 and "sha256" in next(iter(report.skipped.values()))
    assert report.segments == [] and report.removed == 0 and not report.verified
    assert _tree(config) == before


def test_distinct_bodies_are_all_kept(tmp_path: Path) -> None:
    config = _old_season(tmp_path)
    report = convert_raw_to_segments(config, SOURCE, SEASON, dry_run=False)
    assert report.verified and len(report.segments) == 1
    rows = _segment_rows(config)
    assert len(rows) == 3, "one row per distinct URL and body, not per copy"
    by_sha = {row["sha256"]: row for row in rows}
    assert set(by_sha) == {
        hashlib.sha256(b).hexdigest() for b in (FEED_BODY, FEED_BODY_LATER, BOX_BODY)
    }
    for row in rows:
        assert hashlib.sha256(row["body"]).hexdigest() == row["sha256"] and row["status"] == 200
    shared = by_sha[hashlib.sha256(FEED_BODY).hexdigest()]
    assert shared["url"] == FEED
    assert sorted(shared["legacy_path"].split(",")) == [
        "game_feed_play_events/game_feed_play_events_745000.json",
        "game_feed_plays/game_feed_plays_745000.json",
    ]
    commit = json.loads(
        (config.raw_root / SOURCE / f"season={SEASON}" / "segments.json")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert sorted(commit["units"]) == sorted({FEED, BOX})
    assert _tree(config), "the old files stay unless remove_old is asked for"


def test_copies_are_removed_only_after_the_whole_season_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _old_season(tmp_path)
    before = _tree(config)
    monkeypatch.setattr(
        rawsegconvert, "_read_back_failures", lambda *args, **kwargs: ["row 0: body differs"]
    )
    failed = convert_raw_to_segments(config, SOURCE, SEASON, dry_run=False, remove_old=True)
    assert not failed.verified and failed.removed == 0 and failed.segments == []
    assert _tree(config) == before, (
        "a failed read-back rolls the new segment back and keeps every old file"
    )
    monkeypatch.undo()

    done = convert_raw_to_segments(config, SOURCE, SEASON, dry_run=False, remove_old=True)
    assert done.verified and done.removed == 4 and len(done.segments) == 1
    remaining = [p for p in _tree(config) if "_745000.json" in p]
    assert remaining == [], "every old raw file went"
    raw = RawStore(config)
    assert not raw.exists(SOURCE, "game_boxscore_info", "game_boxscore_info_745000.json", SEASON)
    assert len(_segment_rows(config)) == 3


def test_a_rerun_changes_nothing(tmp_path: Path) -> None:
    config = _old_season(tmp_path)
    first = convert_raw_to_segments(config, SOURCE, SEASON, dry_run=False)
    after_first = _tree(config)
    second = convert_raw_to_segments(config, SOURCE, SEASON, dry_run=False)
    assert second.segments == [] and second.distinct_bodies == first.distinct_bodies
    assert _tree(config) == after_first
    removed = convert_raw_to_segments(config, SOURCE, SEASON, dry_run=False, remove_old=True)
    assert removed.removed == 4 and removed.segments == [], (
        "the copies go; nothing is written again"
    )
    last = convert_raw_to_segments(config, SOURCE, SEASON, dry_run=False, remove_old=True)
    assert (last.files, last.segments, last.removed) == (0, [], 0)


def test_a_converted_season_still_passes_cache_check(tmp_path: Path) -> None:
    """After conversion (and removal) the manifests say where the bytes are, and cache check agrees."""
    from baseballpy.cache_check import OK, check_raw, check_segments

    config = _old_season(tmp_path)
    convert_raw_to_segments(config, SOURCE, SEASON, dry_run=False, remove_old=True)
    verdicts = [*check_raw(config, sources=(SOURCE,)), *check_segments(config, sources=(SOURCE,))]
    assert verdicts and all(v.integrity == OK for v in verdicts), verdicts
    manifest = config.dataset_manifest(SOURCE, "game_boxscore_info", "raw", SEASON).chunks()
    entry = manifest["game_boxscore_info_745000.json"]
    assert (
        entry["stored"] == "segment"
        and entry["segment_sha256"] == hashlib.sha256(BOX_BODY).hexdigest()
    )
    assert entry["source_ref"] == BOX


def test_the_convert_raw_command_defaults_to_a_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from click.testing import CliRunner

    from baseballpy.cli import main

    config = _old_season(tmp_path)
    monkeypatch.setenv("BASEBALLPY_HOME", str(config.home))
    before = _tree(config)
    shown = CliRunner().invoke(main, ["convert-raw", "mlb_api", "--season", "2024"])
    assert shown.exit_code == 0, shown.output
    assert "dry run" in shown.output and "distinct answers" in shown.output
    assert _tree(config) == before
    applied = CliRunner().invoke(main, ["convert-raw", "mlb_api", "--season", "2024", "--apply"])
    assert applied.exit_code == 0, applied.output
    assert len(_segment_rows(config)) == 3 and set(_tree(config)) >= set(before)
