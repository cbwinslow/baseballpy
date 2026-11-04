"""Shared pytest fixtures: isolate every test from the user's real ~/.baseballpy."""

import os
from collections.abc import Iterator

import pytest

# dlt phones home with telemetry by default; unit tests must never touch the network.
os.environ.setdefault("RUNTIME__DLTHUB_TELEMETRY", "false")


@pytest.fixture(autouse=True)
def _isolated_baseballpy_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Point BASEBALLPY_HOME at a per-test temp dir and reset lazy singletons around the test."""
    from baseballpy.core.audit import get_audit_logger
    from baseballpy.core.config import reset_config
    from baseballpy.core.quarantine import get_quarantine

    home = tmp_path_factory.mktemp("baseballpy_home")
    monkeypatch.setenv("BASEBALLPY_HOME", str(home))
    # tests parse in process (fast, no spawned workers) unless they ask for a pool
    monkeypatch.setenv("BASEBALLPY_PARSE_WORKERS", "0")
    for key in ("BASEBALLPY_CACHE_DIR",):
        monkeypatch.delenv(key, raising=False)
    get_audit_logger.reset()
    get_quarantine.reset()
    reset_config()
    yield
    get_audit_logger.reset()
    get_quarantine.reset()
    reset_config()


def _git_blob_sha(content: bytes) -> str:
    """The SHA git gives a file of this content, so a changed file has a different blob SHA."""
    import hashlib

    return hashlib.sha1(b"blob %d\x00" % len(content) + content).hexdigest()  # noqa: S324


class RetroRepo:
    """A fake ``chadwickbureau/retrosheet`` repo: serves the git tree and raw files via respx."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def add(self, path: str, content: bytes | str = b"x\n") -> "RetroRepo":
        """Register one file of the fake repository."""
        self.files[path] = content.encode("utf-8") if isinstance(content, str) else content
        return self

    def mount(self, ref: str | None = None, *, tree_status: int = 200, serve: bool = True) -> None:
        """Mock the tree endpoint (and, unless ``serve`` is False, every file) for ``ref``."""
        import httpx
        import respx

        from baseballpy.core.sources_lock import get_source_ref

        pin = ref or get_source_ref("retrosheet").ref
        repo = get_source_ref("retrosheet").repo
        respx.get(f"https://api.github.com/repos/{repo}/git/trees/{pin}?recursive=1").mock(
            return_value=httpx.Response(
                tree_status,
                json={
                    "truncated": False,
                    "tree": [
                        {"path": p, "type": "blob", "size": len(c), "sha": _git_blob_sha(c)}
                        for p, c in self.files.items()
                    ],
                },
            )
        )
        if serve:
            for path, content in self.files.items():
                respx.get(f"https://raw.githubusercontent.com/{repo}/{pin}/{path}").mock(
                    return_value=httpx.Response(200, content=content)
                )


@pytest.fixture
def retro_repo() -> RetroRepo:
    """Empty fake Retrosheet repo; ``add`` files then ``mount()`` inside a ``@respx.mock`` test."""
    return RetroRepo()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip the live provider tests (``tests/live``) unless the marker expression selects them."""
    expression = str(config.getoption("markexpr") or "")
    selected = (
        bool(expression) and not expression.lstrip().startswith("not ") and "live" in expression
    )
    if selected:
        return
    skip = pytest.mark.skip(reason="live provider test: run with `pytest tests/live -m live`")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def postgres_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """A disposable PostgreSQL URL.

    ``BASEBALLPY_TEST_POSTGRES_URL`` (CI sets it from a service container) wins; otherwise the
    dev-only embedded ``pgserver`` is started, and the test skips when it is absent or cannot start
    on this machine.
    """
    url = os.environ.get("BASEBALLPY_TEST_POSTGRES_URL")
    if url:
        yield url
        return
    pgserver = pytest.importorskip("pgserver")
    try:
        server = pgserver.get_server(tmp_path_factory.mktemp("pgdata"), cleanup_mode="stop")
    except Exception as exc:  # embedded server cannot start here (for example initdb on CI Windows)
        pytest.skip(f"embedded PostgreSQL could not start: {exc}")
    uri = str(server.get_uri())
    if "host=" in uri or "@/" in uri:  # unix-socket address (Linux): dlt needs a TCP host
        server.cleanup()
        pytest.skip(
            "embedded PostgreSQL listens on a unix socket here; CI job test-postgres runs these"
        )
    try:
        yield uri
    finally:
        server.cleanup()
