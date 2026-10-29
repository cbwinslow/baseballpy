"""``baseballpy cache check``: integrity of raw files and upstream change detection."""

import json
from collections.abc import Generator, Mapping
from pathlib import Path

import pytest
from click.testing import CliRunner

from baseballpy.cache_check import (
    CHANGED,
    CORRUPT,
    CURRENT,
    MISSING,
    NO_FINGERPRINT,
    NOT_CHECKED,
    OK,
    REMOVED,
    UNREACHABLE,
    check_raw,
)
from baseballpy.cli import main
from baseballpy.core.config import LakeConfig, reset_config
from baseballpy.core.http import TransportError
from baseballpy.core.stores import RawStore
from baseballpy.core.upstream import GIT_BLOB, Fingerprint

REPO = "owner/repo"


def _fp(path: str, sha: str) -> Fingerprint:
    return Fingerprint(GIT_BLOB, sha, origin=f"{REPO}:{path}")


@pytest.fixture
def lake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[LakeConfig, None, None]:
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path))
    reset_config()
    cfg = LakeConfig(home=tmp_path)
    raw = RawStore(cfg)
    raw.put("alpha", "people", "a.csv", b"1\n", upstream=_fp("data/a.csv", "sha-a"))
    raw.put("alpha", "people", "b.csv", b"2\n", upstream=_fp("data/b.csv", "sha-b"))
    raw.put("alpha", "people", "c.csv", b"3\n", upstream=_fp("data/c.csv", "sha-c"))
    raw.put("alpha", "people", "d.csv", b"4\n", upstream=_fp("data/d.csv", "sha-d"))
    raw.put("beta", "games", "x.json", b"{}", season=2024)  # no fingerprint
    yield cfg
    reset_config()


def test_integrity_finds_corrupt_and_missing_files(lake: LakeConfig) -> None:
    (lake.raw_dir("alpha", "people") / "b.csv").write_bytes(b"tampered")
    (lake.raw_dir("alpha", "people") / "c.csv").unlink()
    verdicts = {r.name: r.integrity for r in check_raw(lake)}
    assert verdicts == {
        "a.csv": OK,
        "b.csv": CORRUPT,
        "c.csv": MISSING,
        "d.csv": OK,
        "x.json": OK,
    }


def test_marker_chunks_without_a_sha256_are_not_files(lake: LakeConfig) -> None:
    lake.dataset_manifest("alpha", "people", "raw").set_completed(
        "commit_sha", metadata={"sha": "1"}
    )
    assert "commit_sha" not in {r.name for r in check_raw(lake)}


def test_upstream_comparison_reports_current_changed_removed_and_unfingerprinted(
    lake: LakeConfig,
) -> None:
    latest = {"data/a.csv": "sha-a", "data/b.csv": "sha-NEW", "data/d.csv": "sha-d"}  # c.csv gone
    calls: list[str] = []

    def fake_latest(repo: str) -> Mapping[str, str]:
        calls.append(repo)
        return latest

    results = check_raw(lake, upstream=True, latest=fake_latest)
    verdicts = {r.name: r.upstream for r in results}
    assert verdicts == {
        "a.csv": CURRENT,
        "b.csv": CHANGED,
        "c.csv": REMOVED,
        "d.csv": CURRENT,
        "x.json": NO_FINGERPRINT,
    }
    assert calls == [REPO]  # one tree per repository, not per file
    assert {r.upstream for r in check_raw(lake)} == {NOT_CHECKED}  # offline by default


def test_unreachable_upstream_is_reported_not_raised(lake: LakeConfig) -> None:
    def broken(repo: str) -> Mapping[str, str]:
        raise TransportError("offline")

    verdicts = {r.name: r.upstream for r in check_raw(lake, upstream=True, latest=broken)}
    assert verdicts["a.csv"] == UNREACHABLE and verdicts["x.json"] == NO_FINGERPRINT


def test_source_filter(lake: LakeConfig) -> None:
    assert {r.source for r in check_raw(lake, sources=["beta"])} == {"beta"}


def test_cli_exit_codes_and_output(lake: LakeConfig) -> None:
    runner = CliRunner()
    clean = runner.invoke(main, ["cache", "check"])
    assert clean.exit_code == 0 and "Raw cache check" in clean.output
    (lake.raw_dir("alpha", "people") / "a.csv").write_bytes(b"tampered")
    broken = runner.invoke(main, ["cache", "check"])
    assert broken.exit_code == 1 and "a.csv" in broken.output and "corrupt" in broken.output
    as_json = runner.invoke(main, ["cache", "check", "--json", "--source", "alpha"])
    rows = [json.loads(line) for line in as_json.output.splitlines()]
    assert {r["name"]: r["integrity"] for r in rows}["a.csv"] == CORRUPT
    assert {r["source"] for r in rows} == {"alpha"}
