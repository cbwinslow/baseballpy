"""The polite Retrosheet site fetcher (change retrosheet-site-files).

The interface these tests fix (``baseballpy.sources.retrosheet.site``):

* ``SiteFile(group, path, note)``: one bulk file of retrosheet.org, ``path`` relative to the site root.
* ``site_client(lock_dir=None)``: an ``HttpClient`` for the site: at most one request every four seconds,
  concurrency one, no retries (a refusal is never retried), User-Agent ``baseballpy/<version> ...``.
* ``fetch_site_files(client, config, files, *, refresh=False)`` returns a ``SiteReport`` and reads
  ``https://www.retrosheet.org/robots.txt`` first. A path robots.txt disallows is listed in ``blocked`` and is never
  requested. A 403, 429 or 503 answer, or a connection error, stops the whole run (``stopped`` says why; later files are
  not requested). A file already stored is ``skipped``. Every other file is stored with
  ``RawStore.put("retrosheet", "site_files", <file name>, ...)`` (sha256 in the manifest, the URL as ``source_ref``) and listed
  in ``downloaded``; a 404 is listed in ``failed`` and the run goes on.
* Every download is audit-logged as ``retrosheet_site_download`` with its timing.
"""

from pathlib import Path

import httpx
import respx

from baseballpy.core.audit import AuditConfig, AuditLogger
from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.http import HttpClient
from baseballpy.core.stores import RawStore
from baseballpy.sources.retrosheet import site
from baseballpy.sources.retrosheet.site import SiteFile, fetch_site_files, site_client

BASE = "https://www.retrosheet.org"
ROBOTS = "User-agent: *\nDisallow: /boxesetc/\nDisallow: /gamelogs/\n"


def _fast_client() -> HttpClient:
    """A client without the four-second pause, so tests do not sleep."""
    rates = RateLimitConfig(
        default_requests_per_second=1000,
        host_rates={"www.retrosheet.org": 1000},
        max_concurrency=1,
        max_retries=0,
    )
    return HttpClient(rates, http2=False)


def _robots() -> respx.Route:
    return respx.get(f"{BASE}/robots.txt").mock(return_value=httpx.Response(200, text=ROBOTS))


@respx.mock
def test_robots_disallowed_paths_are_never_requested(tmp_path: Path) -> None:
    _robots()
    banned = respx.get(f"{BASE}/gamelogs/gl2023.zip").mock(
        return_value=httpx.Response(200, content=b"x")
    )
    ok = respx.get(f"{BASE}/downloads/ok.zip").mock(
        return_value=httpx.Response(200, content=b"PK-ok")
    )
    files = [SiteFile("t", "gamelogs/gl2023.zip", ""), SiteFile("t", "downloads/ok.zip", "")]
    report = fetch_site_files(_fast_client(), LakeConfig(home=tmp_path), files)
    assert report.blocked == ["gamelogs/gl2023.zip"] and report.downloaded == ["downloads/ok.zip"]
    assert banned.call_count == 0 and ok.call_count == 1


@respx.mock
def test_a_throttle_answer_stops_the_whole_run(tmp_path: Path) -> None:
    _robots()
    first = respx.get(f"{BASE}/downloads/a.zip").mock(return_value=httpx.Response(429))
    second = respx.get(f"{BASE}/downloads/b.zip").mock(
        return_value=httpx.Response(200, content=b"b")
    )
    files = [SiteFile("t", "downloads/a.zip", ""), SiteFile("t", "downloads/b.zip", "")]
    report = fetch_site_files(_fast_client(), LakeConfig(home=tmp_path), files)
    assert "429" in report.stopped and report.downloaded == []
    assert first.call_count == 1 and second.call_count == 0, "no request after a refusal"


@respx.mock
def test_files_are_stored_once_and_skipped_on_a_rerun(tmp_path: Path) -> None:
    _robots()
    routes = {
        name: respx.get(f"{BASE}/downloads/{name}").mock(
            return_value=httpx.Response(200, content=body)
        )
        for name, body in (("a.zip", b"PK-a"), ("b.zip", b"PK-bb"))
    }
    missing = respx.get(f"{BASE}/downloads/gone.zip").mock(return_value=httpx.Response(404))
    files = [SiteFile("t", f"downloads/{n}", "") for n in ("a.zip", "gone.zip", "b.zip")]
    config = LakeConfig(home=tmp_path)
    first = fetch_site_files(_fast_client(), config, files)
    assert first.downloaded == ["downloads/a.zip", "downloads/b.zip"]
    assert list(first.failed) == ["downloads/gone.zip"] and not first.stopped
    raw = RawStore(config)
    assert raw.get("retrosheet", "site_files", "a.zip") == b"PK-a"
    entry = config.dataset_manifest("retrosheet", "site_files", "raw").chunks()["b.zip"]
    assert entry["source_ref"] == f"{BASE}/downloads/b.zip" and len(entry["sha256"]) == 64
    calls = {n: r.call_count for n, r in routes.items()}
    second = fetch_site_files(_fast_client(), config, files)
    assert second.skipped == ["downloads/a.zip", "downloads/b.zip"] and second.downloaded == []
    assert {n: r.call_count for n, r in routes.items()} == calls, (
        "a stored file is not requested again"
    )
    assert missing.call_count == 2, "a missing file is tried again, a stored one is not"


def test_the_client_is_paced_and_honestly_identified() -> None:
    client = site_client()
    try:
        assert client.rate.host_rates["www.retrosheet.org"] <= 0.25
        assert client.rate.max_concurrency == 1 and client.rate.max_retries == 0
        assert client.user_agent.startswith("baseballpy/")
        assert "@" not in client.user_agent, "no personal data in the User-Agent"
    finally:
        client.close()


@respx.mock
def test_every_download_is_audit_logged_and_timed(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    audit = AuditLogger(AuditConfig(base_dir=tmp_path / "audit"))
    monkeypatch.setattr(site, "default_audit_logger", audit)
    _robots()
    respx.get(f"{BASE}/downloads/a.zip").mock(return_value=httpx.Response(200, content=b"PK-a"))
    fetch_site_files(
        _fast_client(), LakeConfig(home=tmp_path / "lake"), [SiteFile("t", "downloads/a.zip", "")]
    )
    events = [
        e
        for e in audit.read_events(source="retrosheet")
        if e.operation == "retrosheet_site_download"
    ]
    assert len(events) == 1 and events[0].status == "SUCCESS"
    assert (
        events[0].endpoint == f"{BASE}/downloads/a.zip" and events[0].duration_seconds is not None
    )
    assert events[0].download_seconds is not None, "the download time is logged apart from the rest"
    assert events[0].processing_seconds is not None


@respx.mock
def test_the_run_stops_before_a_download_when_the_disk_is_nearly_full(tmp_path: Path) -> None:
    _robots()
    route = respx.get(f"{BASE}/downloads/a.zip").mock(
        return_value=httpx.Response(200, content=b"a")
    )
    report = fetch_site_files(
        _fast_client(),
        LakeConfig(home=tmp_path),
        [SiteFile("t", "downloads/a.zip", "")],
        min_free_bytes=10**18,  # more than any disk has
    )
    assert "low disk space" in report.stopped and route.call_count == 0
