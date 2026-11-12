"""Streaming downloads through the shared HttpClient, and adopting the file into the raw store.

Change retrosheet-site-files. The interface these tests fix:

* ``HttpClient.download_sync(url, dest, *, max_bytes=None, allow=(200,))`` streams the body to ``dest`` (written as
  ``<dest>.part`` and renamed when complete), through the same rate limiter, host claim and audit as ``get``. It returns a
  ``DownloadResult(url, status, path, size, sha256, etag, content_length, elapsed_seconds, too_large)``. A
  ``Content-Length`` above ``max_bytes`` (or a body that grows past it) is not read: ``too_large`` is true and no file is
  left. A status in ``allow`` other than 200 returns with ``path`` ``None``; a status not in ``allow`` raises
  ``HttpStatusError``.
* ``RawStore.adopt(source, dataset, name, path, *, sha256, size, source_ref=None, etag="", season=None)`` moves a file
  that is already on disk into the raw folder and records its sha256 and size in the manifest, like ``put`` does for bytes.
"""

import hashlib
from pathlib import Path

import httpx
import pytest
import respx

from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.http import HttpClient, HttpStatusError
from baseballpy.core.stores import RawStore

URL = "https://example.test/big.zip"


def _client() -> HttpClient:
    rates = RateLimitConfig(default_requests_per_second=1000, max_retries=0)
    return HttpClient(rates, http2=False)


@respx.mock
def test_a_download_streams_to_a_file_and_reports_size_and_sha256(tmp_path: Path) -> None:
    body = b"PK" + bytes(range(256)) * 4000
    respx.get(URL).mock(return_value=httpx.Response(200, content=body, headers={"ETag": '"abc"'}))
    dest = tmp_path / "out" / "big.zip"
    result = _client().download_sync(URL, dest)
    assert result.status == 200 and result.path == dest and not result.too_large
    assert result.size == len(body) and result.sha256 == hashlib.sha256(body).hexdigest()
    assert result.etag == '"abc"' and dest.read_bytes() == body
    assert not (tmp_path / "out" / "big.zip.part").exists(), "no half-written file is left"


@respx.mock
def test_a_file_above_the_limit_is_not_read_and_leaves_nothing(tmp_path: Path) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"x" * 5000))
    dest = tmp_path / "big.zip"
    result = _client().download_sync(URL, dest, max_bytes=1000)
    assert result.too_large and result.path is None and result.size == 0
    assert not dest.exists() and not list(tmp_path.glob("*.part"))


@respx.mock
def test_statuses_in_allow_return_without_a_file_and_others_raise(tmp_path: Path) -> None:
    respx.get(URL).mock(return_value=httpx.Response(404))
    missing = _client().download_sync(URL, tmp_path / "a.zip", allow=(200, 404))
    assert missing.status == 404 and missing.path is None
    with pytest.raises(HttpStatusError):
        _client().download_sync(URL, tmp_path / "b.zip")
    assert not list(tmp_path.glob("*.zip*"))


def test_adopt_moves_a_file_into_the_raw_store_and_records_its_checksum(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path / "lake")
    body = b"PK-adopted"
    staged = tmp_path / "staged.zip"
    staged.write_bytes(body)
    sha = hashlib.sha256(body).hexdigest()
    store = RawStore(config)
    store.adopt(
        "retrosheet",
        "site_files",
        "x.zip",
        staged,
        sha256=sha,
        size=len(body),
        source_ref=URL,
        etag="e",
    )
    assert not staged.exists()
    assert store.get("retrosheet", "site_files", "x.zip") == body
    entry = config.dataset_manifest("retrosheet", "site_files", "raw").chunks()["x.zip"]
    assert (entry["sha256"], entry["bytes"], entry["source_ref"]) == (sha, len(body), URL)
    assert store.verify("retrosheet", "site_files", "x.zip")
