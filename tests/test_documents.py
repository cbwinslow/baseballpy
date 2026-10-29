"""The shared helper that keeps a provider's README, licence and data dictionary."""

from pathlib import Path

import httpx
import pytest
import respx

from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.documents import document_paths, keep_documents, tree_or_none
from baseballpy.core.github_tree import TreeEntry
from baseballpy.core.http import HttpClient
from baseballpy.core.sources_lock import SourceRef
from baseballpy.core.stores import RawStore
from baseballpy.core.upstream import GIT_BLOB, stored_fingerprint

REF = SourceRef("demo", "owner/repo", "a" * 40)
ENTRIES = [
    TreeEntry("README.md", 10, "sha-readme"),
    TreeEntry("LICENSE", 20, "sha-licence"),
    TreeEntry("data/readme2025.txt", 30, "sha-dict"),
    TreeEntry("data/Batting.csv", 40, "sha-data"),
    TreeEntry(".gitignore", 1, "sha-ignore"),
]
PATTERNS = ("README.md", "LICENSE", "data/readme*.txt")


def _http() -> HttpClient:
    rates = RateLimitConfig(
        default_requests_per_second=1000,
        host_rates={"raw.githubusercontent.com": 1000, "api.github.com": 1000},
        max_retries=0,
    )
    return HttpClient(rates, http2=False)


def _serve(files: dict[str, bytes]) -> None:
    for path, body in files.items():
        respx.get(f"{REF.raw_base()}/{path}").mock(return_value=httpx.Response(200, content=body))


def test_patterns_find_documents_even_when_the_dictionary_is_renamed_each_year() -> None:
    assert [e.path for e in document_paths(ENTRIES, PATTERNS)] == [
        "README.md",
        "LICENSE",
        "data/readme2025.txt",
    ]
    renamed = [TreeEntry("data/readme2026.txt", 1, "x")]
    assert [e.path for e in document_paths(renamed, PATTERNS)] == ["data/readme2026.txt"]
    assert document_paths(ENTRIES, ["readme*.txt"]) == []  # matched on the full path


@respx.mock
def test_documents_are_stored_with_hash_and_git_fingerprint_and_not_fetched_twice(
    tmp_path: Path,
) -> None:
    _serve({"README.md": b"# r", "LICENSE": b"CC BY-SA", "data/readme2025.txt": b"dictionary"})
    cfg = LakeConfig(home=tmp_path)
    raw, http = RawStore(cfg), _http()
    try:
        common = {
            "raw": raw,
            "http": http,
            "ref": REF,
            "entries": ENTRIES,
            "source": "demo",
            "dataset": "documents",
            "patterns": PATTERNS,
            "source_ref": REF.ref,
        }
        kept = keep_documents(**common, only_missing=False)  # type: ignore[arg-type]
        assert kept == ["README.md", "LICENSE", "readme2025.txt"]
        assert raw.get("demo", "documents", "LICENSE") == b"CC BY-SA"
        assert raw.verify("demo", "documents", "readme2025.txt")
        entry = cfg.dataset_manifest("demo", "documents", "raw").chunks()["readme2025.txt"]
        fingerprint = stored_fingerprint(entry)
        assert fingerprint is not None and fingerprint.kind == GIT_BLOB
        assert (
            fingerprint.value == "sha-dict"
            and fingerprint.origin == "owner/repo:data/readme2025.txt"
        )
        calls = len(respx.calls)
        assert keep_documents(**common, only_missing=True) == []  # type: ignore[arg-type]
        assert len(respx.calls) == calls  # a cached run downloads nothing
    finally:
        http.close()


@respx.mock
def test_a_failed_document_download_is_logged_and_the_rest_are_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    respx.get(f"{REF.raw_base()}/README.md").mock(return_value=httpx.Response(404))
    _serve({"LICENSE": b"licence", "data/readme2025.txt": b"dict"})
    raw, http = RawStore(LakeConfig(home=tmp_path)), _http()
    try:
        with caplog.at_level("WARNING"):
            kept = keep_documents(
                raw=raw,
                http=http,
                ref=REF,
                entries=ENTRIES,
                source="demo",
                dataset="documents",
                patterns=PATTERNS,
                source_ref=None,
                only_missing=False,
            )
    finally:
        http.close()
    assert kept == ["LICENSE", "readme2025.txt"]
    assert "could not download demo document README.md" in caplog.text


@respx.mock
def test_an_unlistable_tree_is_none_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    respx.get(f"https://api.github.com/repos/owner/repo/git/trees/{REF.ref}?recursive=1").mock(
        return_value=httpx.Response(500)
    )
    http = _http()
    try:
        with caplog.at_level("WARNING"):
            assert tree_or_none(REF, LakeConfig(home=tmp_path), http, what="documents") is None
    finally:
        http.close()
    assert "could not list documents" in caplog.text
