"""A refresh replaces a raw file's bytes and the manifest remembers the versions it replaced (ADR 122)."""

import hashlib
from pathlib import Path

from baseballpy.core.config import LakeConfig
from baseballpy.core.stores import RawStore


def _entry(config: LakeConfig) -> dict:
    return config.dataset_manifest("src", "ds", "raw", 2024).get_chunk("window.csv") or {}


def test_a_refresh_replaces_the_bytes_and_keeps_a_record_of_each_replaced_version(
    tmp_path: Path,
) -> None:
    config = LakeConfig(home=tmp_path)
    store = RawStore(config)
    first, second, third = b"a,b\n1,SL\n", b"a,b\n1,ST\n", b"a,b\n1,ST\n2,FF\n"

    path = store.put("src", "ds", "window.csv", first, season=2024)
    assert "previous" not in _entry(config), "a first download has nothing before it"

    store.put("src", "ds", "window.csv", first, season=2024)
    assert "previous" not in _entry(config), "the same bytes fetched again add no version"

    store.put("src", "ds", "window.csv", second, season=2024)
    assert path.read_bytes() == second, "the file holds the newest answer"
    entry = _entry(config)
    assert entry["sha256"] == hashlib.sha256(second).hexdigest()
    assert [v["sha256"] for v in entry["previous"]] == [hashlib.sha256(first).hexdigest()]
    assert entry["previous"][0]["bytes"] == len(first)
    assert entry["previous"][0]["fetched_at"], "the download time of the replaced version is kept"

    store.put("src", "ds", "window.csv", second, season=2024)
    store.put("src", "ds", "window.csv", third, season=2024)
    history = [v["sha256"] for v in _entry(config)["previous"]]
    assert history == [hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest()], (
        "every replaced version is listed once, oldest first"
    )
