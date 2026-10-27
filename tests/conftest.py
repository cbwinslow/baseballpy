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
    for key in ("BASEBALLPY_CACHE_DIR",):
        monkeypatch.delenv(key, raising=False)
    get_audit_logger.reset()
    get_quarantine.reset()
    reset_config()
    yield
    get_audit_logger.reset()
    get_quarantine.reset()
    reset_config()
