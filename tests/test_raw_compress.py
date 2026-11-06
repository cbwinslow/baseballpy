"""Compressed raw files: same checksum, same readers, a safe conversion of what is already stored."""

import gzip
import hashlib
from pathlib import Path

import pytest
from click.testing import CliRunner

from baseballpy.cache_check import OK, check_raw
from baseballpy.cli import main
from baseballpy.core.config import LakeConfig
from baseballpy.core.rawconvert import compress_raw
from baseballpy.core.stores import RawStore

BODY = b'{"teams": [' + b'{"id": 1, "name": "Mariners"},' * 200 + b"{}]}"


def _config(tmp_path: Path, sources: tuple[str, ...] = ("mlb_api", "statcast")) -> LakeConfig:
    return LakeConfig(home=tmp_path, raw_compress_sources=sources)


def test_a_new_raw_file_is_gzipped_but_keeps_the_checksum_of_the_original(tmp_path: Path) -> None:
    store = RawStore(_config(tmp_path))
    store.put("mlb_api", "teams", "1.json", BODY, season=2024)
    folder = store.config.raw_dir("mlb_api", "teams", 2024)
    assert [p.name for p in folder.glob("[!_]*.json*")] == ["1.json.gz"]
    assert gzip.decompress((folder / "1.json.gz").read_bytes()) == BODY
    entry = store.config.dataset_manifest("mlb_api", "teams", "raw", 2024).get_chunk("1.json")
    assert entry is not None
    assert entry["sha256"] == hashlib.sha256(BODY).hexdigest() and entry["bytes"] == len(BODY)
    assert entry["stored"] == "gzip" and entry["stored_bytes"] < len(BODY) / 5
    assert (
        store.exists("mlb_api", "teams", "1.json", 2024)
        and store.get("mlb_api", "teams", "1.json", 2024) == BODY
    )
    assert store.verify("mlb_api", "teams", "1.json", 2024)


def test_other_sources_and_already_packed_files_are_stored_as_they_came(tmp_path: Path) -> None:
    store = RawStore(_config(tmp_path))
    store.put("lahman", "people", "People.csv", b"a,b\n1,2\n")
    store.put("mlb_api", "teams", "x.zip", b"PK\x03\x04 not text")
    store.put("mlb_api", "teams", "y.jsonl.gz", gzip.compress(b"{}\n"))
    root = tmp_path / "raw"
    assert (root / "lahman" / "people" / "People.csv").exists()
    assert (root / "mlb_api" / "teams" / "x.zip").exists()
    assert (root / "mlb_api" / "teams" / "y.jsonl.gz").exists()
    assert not list(root.rglob("*.gz.gz"))


def test_a_refresh_never_leaves_both_forms_of_one_file(tmp_path: Path) -> None:
    plain = RawStore(_config(tmp_path, ()))
    plain.put("mlb_api", "teams", "1.json", b'{"v": 1}', season=2024)
    packed = RawStore(_config(tmp_path))
    packed.put("mlb_api", "teams", "1.json", BODY, season=2024)
    names = sorted(
        p.name for p in (tmp_path / "raw" / "mlb_api" / "teams" / "season=2024").glob("1.*")
    )
    assert names == ["1.json.gz"]
    assert packed.get("mlb_api", "teams", "1.json", 2024) == BODY


def _plain_lake(tmp_path: Path) -> LakeConfig:
    store = RawStore(_config(tmp_path, ()))  # written the old way: plain files
    for index in range(5):
        store.put("mlb_api", "teams", f"{index}.json", BODY + str(index).encode(), season=2024)
        store.put("statcast", "pitches", f"{index}.csv", b"a,b\n" * 500, season=2024)
    store.put("lahman", "people", "People.csv", b"a,b\n1,2\n")
    return _config(tmp_path)


def test_conversion_keeps_every_byte_and_checksum_and_a_rerun_does_nothing(tmp_path: Path) -> None:
    cfg = _plain_lake(tmp_path)
    before = {
        (d, n): RawStore(cfg).get("mlb_api" if d == "teams" else "statcast", d, n, 2024)
        for d, n in (("teams", "3.json"), ("pitches", "2.csv"))
    }
    dry = compress_raw(cfg, dry_run=True)
    assert dry.files == 10 and list((tmp_path / "raw").rglob("*.gz")) == []
    done = compress_raw(cfg)
    assert done.files == 10 and done.skipped == [] and done.bytes_after < done.bytes_before / 5
    assert len(list((tmp_path / "raw").rglob("*.gz"))) == 10
    assert not list((tmp_path / "raw" / "mlb_api").rglob("[!_]*.json"))
    assert (tmp_path / "raw" / "lahman" / "people" / "People.csv").exists()
    store = RawStore(cfg)
    assert store.get("mlb_api", "teams", "3.json", 2024) == before[("teams", "3.json")]
    assert store.get("statcast", "pitches", "2.csv", 2024) == before[("pitches", "2.csv")]
    assert all(store.verify("mlb_api", "teams", f"{i}.json", 2024) for i in range(5))
    assert compress_raw(cfg).files == 0
    checks = check_raw(cfg, latest=lambda _repo: {})
    assert checks and all(c.integrity == OK for c in checks)


def test_a_file_that_does_not_match_its_checksum_is_left_alone(tmp_path: Path) -> None:
    cfg = _plain_lake(tmp_path)
    bad = tmp_path / "raw" / "mlb_api" / "teams" / "season=2024" / "1.json"
    bad.write_bytes(b"damaged")
    done = compress_raw(cfg)
    assert done.files == 9 and len(done.skipped) == 1 and "1.json" in done.skipped[0]
    assert bad.read_bytes() == b"damaged" and not bad.with_name("1.json.gz").exists()


def test_the_compress_raw_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _plain_lake(tmp_path)
    monkeypatch.setenv("BASEBALLPY_HOME", str(cfg.home))
    result = CliRunner().invoke(main, ["compress-raw"])
    assert result.exit_code == 0, result.output
    assert "compressed 10 files" in result.output


def test_a_file_the_caller_already_gzipped_is_checked_and_read_as_it_came(tmp_path: Path) -> None:
    store = RawStore(_config(tmp_path))
    packed = gzip.compress(b'{"a": 1}\n')
    store.put("mlb_api", "teams", "pages.jsonl.gz", packed)
    assert store.get("mlb_api", "teams", "pages.jsonl.gz") == packed
    assert store.verify("mlb_api", "teams", "pages.jsonl.gz")
