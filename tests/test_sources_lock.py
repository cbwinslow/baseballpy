"""Pinned refs: lock resolution, env overrides, `refs update`, and ref-based invalidation."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.core import sources_lock
from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.http import HttpClient
from baseballpy.sources.lahman.extractor import LAHMAN_GITHUB_BASE, LahmanExtractor
from baseballpy.sources.retrosheet.downloader import GITHUB_RETROSHEET_BASE, RetrosheetDownloader

SHA_A = "a" * 40
SHA_B = "b" * 40


def _rates() -> RateLimitConfig:
    return RateLimitConfig(
        default_requests_per_second=1000,
        host_rates={
            "raw.githubusercontent.com": 1000,
            "api.github.com": 1000,
        },
        max_retries=0,
    )


def test_packaged_lock_pins_full_shas_and_never_lists_baseballdatabank() -> None:
    lock = sources_lock.load_lock()
    assert set(lock) == {"retrosheet", "chadwick_register", "lahman"}
    for key, entry in lock.items():
        assert sources_lock.get_source_ref(key).pinned, key
        assert "baseballdatabank" not in entry["repo"]
    assert lock["lahman"]["repo"] == "cbwinslow/lahman-database-csv"


def test_urls_are_built_from_the_pinned_ref() -> None:
    ref = sources_lock.get_source_ref("retrosheet")
    assert f"https://raw.githubusercontent.com/{ref.repo}/{ref.ref}" == GITHUB_RETROSHEET_BASE
    assert ref.raw_url("/seasons/2023/TEAM2023").endswith(f"/{ref.ref}/seasons/2023/TEAM2023")
    assert "/main/" not in LAHMAN_GITHUB_BASE and "/master/" not in GITHUB_RETROSHEET_BASE


def test_env_override_wins_and_branch_is_not_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASEBALLPY_RETROSHEET_REF", "master")
    ref = sources_lock.get_source_ref("retrosheet")
    assert ref.ref == "master" and not ref.pinned


def test_lake_level_lock_overrides_packaged(tmp_path: Path) -> None:
    (tmp_path / "sources.lock.json").write_text(
        json.dumps({"lahman": {"repo": "cbwinslow/lahman-database-csv", "ref": SHA_A}})
    )
    assert sources_lock.get_source_ref("lahman", tmp_path).ref == SHA_A
    with pytest.raises(KeyError):
        sources_lock.get_source_ref("retrosheet", tmp_path)  # override replaces the whole lock


@respx.mock
def test_update_lock_resolves_latest_shas_and_writes_lake_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sources_lock, "PACKAGED_LOCK", tmp_path / "ro" / "sources_lock.json")
    packaged = tmp_path / "ro" / "sources_lock.json"
    packaged.parent.mkdir()
    packaged.write_text(
        json.dumps(
            {
                "retrosheet": {"repo": "chadwickbureau/retrosheet", "ref": SHA_A},
                "lahman": {"repo": "cbwinslow/lahman-database-csv", "ref": SHA_A},
            }
        )
    )
    monkeypatch.setenv("GITHUB_TOKEN", "t0ken")
    routes = {
        repo: respx.get(f"https://api.github.com/repos/{repo}/commits?per_page=1").mock(
            return_value=httpx.Response(200, json=[{"sha": sha}])
        )
        for repo, sha in (
            ("chadwickbureau/retrosheet", SHA_A),  # unchanged
            ("cbwinslow/lahman-database-csv", SHA_B),  # moved
        )
    }
    http = HttpClient(_rates(), http2=False)
    try:
        cfg = LakeConfig(home=tmp_path / "home")
        dry = sources_lock.update_lock(http, cfg, dry_run=True)
        assert {c.key: c.changed for c in dry} == {"lahman": True, "retrosheet": False}
        assert json.loads(packaged.read_text())["lahman"]["ref"] == SHA_A  # dry run writes nothing

        changes = sources_lock.update_lock(http, cfg)
    finally:
        http.close()
    assert {c.key: (c.old, c.new) for c in changes}["lahman"] == (SHA_A, SHA_B)
    assert routes["cbwinslow/lahman-database-csv"].calls[0].request.headers["authorization"] == (
        "Bearer t0ken"
    )
    assert json.loads(packaged.read_text())["lahman"]["ref"] == SHA_B
    assert sources_lock.get_source_ref("lahman", cfg.home).ref == SHA_B


@respx.mock
def test_update_lock_rejects_malformed_github_response(tmp_path: Path) -> None:
    respx.get("https://api.github.com/repos/chadwickbureau/retrosheet/commits?per_page=1").mock(
        return_value=httpx.Response(200, json={"message": "nope"})
    )
    http = HttpClient(_rates(), http2=False)
    try:
        with pytest.raises(ValueError, match="unexpected GitHub response"):
            sources_lock.resolve_latest_sha("chadwickbureau/retrosheet", http)
    finally:
        http.close()


def test_write_lock_falls_back_to_lake_when_package_is_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sources_lock, "PACKAGED_LOCK", tmp_path / "missing" / "deep" / "x.json")

    def deny(*_a: object, **_k: object) -> None:
        raise PermissionError("read-only")

    real = sources_lock.atomic_write

    class _Ctx:
        def __init__(self, target: Path, mode: str = "wb") -> None:
            if "missing" in str(target):
                deny()
            self.inner = real(target, mode=mode)

        def __enter__(self) -> Path:
            return self.inner.__enter__()

        def __exit__(self, *exc: object) -> bool | None:
            return self.inner.__exit__(*exc)  # type: ignore[arg-type]

    monkeypatch.setattr(sources_lock, "atomic_write", _Ctx)
    cfg = LakeConfig(home=tmp_path / "home")
    target = sources_lock.write_lock({"lahman": {"repo": "r/r", "ref": SHA_A}}, cfg)
    assert target == tmp_path / "home" / "sources.lock.json"


def _lahman(tmp_path: Path, ref: str | None = None) -> tuple[LahmanExtractor, HttpClient]:
    http = HttpClient(_rates(), http2=False)
    if ref:
        (tmp_path / "sources.lock.json").write_text(
            json.dumps({"lahman": {"repo": "cbwinslow/lahman-database-csv", "ref": ref}})
        )
    return LahmanExtractor(
        cache_config=LakeConfig(home=tmp_path), rate_limit_config=_rates(), http=http
    ), http


@respx.mock
def test_lahman_chunk_fetched_at_other_ref_is_refetched(tmp_path: Path) -> None:
    base = "https://raw.githubusercontent.com/cbwinslow/lahman-database-csv"
    old = respx.get(f"{base}/{SHA_A}/data/Parks.csv").mock(
        return_value=httpx.Response(200, content=b"parkkey\nA\n")
    )
    new = respx.get(f"{base}/{SHA_B}/data/Parks.csv").mock(
        return_value=httpx.Response(200, content=b"parkkey\nB\n")
    )
    respx.get(url__startswith="https://api.github.com/repos/").mock(
        return_value=httpx.Response(500)  # no file listing: the pinned commit decides
    )
    first, http1 = _lahman(tmp_path, SHA_A)
    try:
        assert first.extract_table("Parks") == b"parkkey\nA\n"
        assert first.extract_table("Parks") == b"parkkey\nA\n"
        assert old.call_count == 1
    finally:
        http1.close()
    entry = first.file_entry("Parks")
    assert entry is not None and entry["source_ref"] == SHA_A

    second, http2 = _lahman(tmp_path, SHA_B)  # lock moved
    try:
        assert second.extract_table("Parks") == b"parkkey\nB\n"
        assert new.call_count == 1
    finally:
        http2.close()


@respx.mock
def test_retrosheet_season_chunk_invalidated_by_ref_change_but_legacy_entry_trusted(
    tmp_path: Path,
) -> None:
    cfg = LakeConfig(home=tmp_path)
    http = HttpClient(_rates(), http2=False)
    dl = RetrosheetDownloader(cache_config=cfg, rate_limit_config=_rates(), http=http)
    try:
        dl.manifest.set_completed("legacy", records_count=1)  # v1/migrated: no source_ref
        assert dl._chunk_current(dl.manifest, "legacy")
        dl.manifest.set_completed("old", metadata={"source_ref": SHA_A})
        assert not dl._chunk_current(dl.manifest, "old")
        dl.manifest.set_completed("cur", metadata={"source_ref": dl.source_ref.ref})
        assert dl._chunk_current(dl.manifest, "cur")
        assert not dl._chunk_current(dl.manifest, "missing")
    finally:
        http.close()


def test_cli_refs_show_lists_every_source() -> None:
    result = CliRunner().invoke(main, ["refs", "show"])
    assert result.exit_code == 0, result.output
    for needle in ("retrosheet", "chadwick_register", "lahman", "cbwinslow"):
        assert needle in result.output


@respx.mock
def test_cli_refs_update_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    for repo in (
        "chadwickbureau/retrosheet",
        "chadwickbureau/register",
        "cbwinslow/lahman-database-csv",
    ):
        respx.get(f"https://api.github.com/repos/{repo}/commits?per_page=1").mock(
            return_value=httpx.Response(200, json=[{"sha": SHA_B}])
        )
    result = CliRunner().invoke(main, ["refs", "update", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "dry run" in result.output.lower() and "bbbbbbbbbbbb" in result.output
