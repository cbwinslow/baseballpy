"""Retrosheet is judged by git fingerprints at both cache tiers and keeps the provider's documents."""

import os
from pathlib import Path

import respx
from conftest import RetroRepo
from test_retrosheet_coverage import _game, full_season

from baseballpy.core.config import LakeConfig
from baseballpy.core.upstream import GIT_BLOB
from baseballpy.sources.retrosheet.api import RetrosheetSource
from baseballpy.sources.retrosheet.downloader import RetrosheetDownloader

NEW_PIN = "b" * 40


def _raw_requests(ref: str, since: int = 0) -> list[str]:
    return [
        str(call.request.url)
        for call in list(respx.calls)[since:]
        if "raw.githubusercontent.com" in str(call.request.url)
        and f"/{ref}/" in str(call.request.url)
    ]


@respx.mock
def test_pin_move_refetches_only_changed_blobs_and_rebuilds_their_chunks(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    full_season(retro_repo).mount()
    cfg = LakeConfig(home=tmp_path)
    source = RetrosheetSource(cache_config=cfg)
    source.ingest_season(2024)
    rosters = source.store.part_path(retro_api_spec("rosters"), "rosters_2024", 2024)
    before = os.stat(rosters).st_mtime_ns

    # the pin moves; only one regular-season event file changes upstream
    retro_repo.add(
        "seasons/2024/2024BAL.EVN", _game("BAL202404020", "BAL", "BOS") + b"com,changed\n"
    )
    retro_repo.mount(NEW_PIN)
    source.downloader = RetrosheetDownloader(cache_config=cfg, ref=NEW_PIN)
    second = source.ingest_season(2024)

    assert len(_raw_requests(NEW_PIN)) == 1  # only the changed blob was fetched
    assert second.datasets["rosters"] is None and second.datasets["gamelogs"] is None
    assert second.datasets["events"] is not None  # built from the changed file
    assert second.datasets["events_postseason"] is None
    assert os.stat(rosters).st_mtime_ns == before  # untouched chunks are not rewritten
    entry = cfg.dataset_manifest("retrosheet", "event_files", "raw", 2024).get_chunk("2024BAL.EVN")
    assert entry is not None and entry["upstream"]["kind"] == GIT_BLOB


@respx.mock
def test_a_pin_move_with_no_changed_file_fetches_and_rebuilds_nothing(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    full_season(retro_repo).mount()
    cfg = LakeConfig(home=tmp_path)
    source = RetrosheetSource(cache_config=cfg)
    source.ingest_season(2024)
    retro_repo.mount(NEW_PIN)
    source.downloader = RetrosheetDownloader(cache_config=cfg, ref=NEW_PIN)
    again = source.ingest_season(2024)
    assert _raw_requests(NEW_PIN) == []
    assert {k: v for k, v in again.datasets.items() if v is not None} == {}


@respx.mock
def test_refresh_downloads_each_file_once_and_a_selection_downloads_only_what_it_reads(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    full_season(retro_repo).mount()
    cfg = LakeConfig(home=tmp_path)
    pin = RetrosheetSource(cache_config=cfg).downloader.source_ref.ref
    source = RetrosheetSource(cache_config=cfg)
    source.ingest_season(2024, datasets=("rosters",), refresh=True)
    assert len(_raw_requests(pin)) == 1  # the roster file only

    seen = len(respx.calls)
    fresh = RetrosheetSource(cache_config=LakeConfig(home=tmp_path / "other"))
    fresh.ingest_season(2024, refresh=True)
    urls = _raw_requests(pin, seen)
    repeated = sorted({u.rsplit("/", 1)[-1] for u in urls if urls.count(u) > 1})
    assert repeated == []  # each file once, not once per dataset
    assert len(urls) == len(retro_repo.files)


@respx.mock
def test_root_documents_are_kept(tmp_path: Path, retro_repo: RetroRepo) -> None:
    full_season(retro_repo)
    retro_repo.add("README.md", b"Copyrighted by Retrosheet.\n").add(
        ".gitattributes", b"* text=auto\n"
    )
    retro_repo.add("seasons/2024/mystery.bin", b"??")
    retro_repo.mount()
    cfg = LakeConfig(home=tmp_path)
    RetrosheetSource(cache_config=cfg).ingest_reference()
    docs = cfg.raw_root / "retrosheet" / "documents"
    assert (docs / "README.md").read_bytes() == b"Copyrighted by Retrosheet.\n"
    assert (docs / ".gitattributes").exists()
    assert (cfg.raw_root / "retrosheet" / "unclassified" / "mystery.bin").exists()
    entry = cfg.dataset_manifest("retrosheet", "documents", "raw").get_chunk("README.md")
    assert entry is not None and entry["upstream"]["kind"] == GIT_BLOB


def retro_api_spec(name: str):  # type: ignore[no-untyped-def]
    from baseballpy.core.datasets import get_dataset

    return get_dataset("retrosheet", name)


@respx.mock
def test_a_chunk_written_under_another_schema_is_rebuilt_without_refresh(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    full_season(retro_repo).mount()
    cfg = LakeConfig(home=tmp_path)
    source = RetrosheetSource(cache_config=cfg)
    source.ingest_season(2024, datasets=("rosters",))
    manifest = cfg.dataset_manifest("retrosheet", "rosters", "processed")
    key = next(k for k in manifest.chunks() if "rosters" in k)
    entry = dict(manifest.get_chunk(key) or {})
    manifest.put_entry(key, {**entry, "schema_sha256": "0" * 64})  # as if an older release wrote it

    assert source.ingest_season(2024, datasets=("rosters",)).datasets["rosters"] is not None
    assert source.ingest_season(2024, datasets=("rosters",)).datasets["rosters"] is None
