"""One process per host: a second process is refused, a crash frees the claim, opt-out works."""

import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import respx

from baseballpy.core.config import RateLimitConfig
from baseballpy.core.hostlock import HostBusyError, claim_host, release_all
from baseballpy.core.http import HttpClient

#: claims a host, says so, then waits for a line and ends abruptly with no clean-up (a crash)
_HOLD = (
    "import os, sys\n"
    "from pathlib import Path\n"
    "from baseballpy.core.hostlock import claim_host\n"
    "claim_host(Path(sys.argv[1]), sys.argv[2])\n"
    "print('held', flush=True)\n"
    "sys.stdin.readline()\n"
    "os._exit(1)\n"
)


def _hold(directory: Path, host: str) -> "subprocess.Popen[str]":
    process = subprocess.Popen(  # noqa: S603 - runs this interpreter on a fixed script
        [sys.executable, "-c", _HOLD, str(directory), host],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "held"
    return process


def _crash(process: "subprocess.Popen[str]") -> None:
    """End the holder abruptly and wait until it is gone."""
    assert process.stdin is not None
    process.stdin.write("\n")
    process.stdin.flush()
    process.wait(timeout=30)


def test_a_claim_is_idempotent_in_one_process_and_free_for_other_hosts(tmp_path: Path) -> None:
    claim_host(tmp_path, "api.example.com")
    claim_host(tmp_path, "api.example.com")
    claim_host(tmp_path, "other.example.com")
    release_all(tmp_path)
    claim_host(tmp_path, "api.example.com")
    release_all(tmp_path)


def test_a_second_process_is_refused_until_the_first_ends_even_by_a_crash(tmp_path: Path) -> None:
    holder = _hold(tmp_path, "api.example.com")
    try:
        with pytest.raises(HostBusyError, match="already downloading from api.example.com"):
            claim_host(tmp_path, "api.example.com")
        claim_host(tmp_path, "other.example.com")  # another host is not blocked
    finally:
        _crash(holder)  # no clean exit: the OS drops the lock with the process
        release_all(tmp_path)
    claim_host(tmp_path, "api.example.com")
    release_all(tmp_path)


@respx.mock
def test_the_http_client_claims_a_host_on_first_use_and_the_opt_out_skips_the_claim(
    tmp_path: Path,
) -> None:
    respx.get("https://api.example.com/x").mock(return_value=httpx.Response(200, content=b"ok"))
    holder = _hold(tmp_path, "api.example.com")
    try:
        client = HttpClient(RateLimitConfig(), http2=False, lock_dir=tmp_path)
        try:
            with pytest.raises(HostBusyError):
                client.get_sync("https://api.example.com/x")
        finally:
            client.close()
        shared = HttpClient(
            RateLimitConfig(allow_parallel_processes=True), http2=False, lock_dir=tmp_path
        )
        try:
            assert shared.get_sync("https://api.example.com/x").content == b"ok"
        finally:
            shared.close()
    finally:
        _crash(holder)
        release_all(tmp_path)


@respx.mock
def test_a_client_without_a_lock_folder_never_claims(tmp_path: Path) -> None:
    respx.get("https://api.example.com/x").mock(return_value=httpx.Response(200, content=b"ok"))
    holder = _hold(tmp_path, "api.example.com")
    try:
        client = HttpClient(RateLimitConfig(), http2=False)
        try:
            assert client.get_sync("https://api.example.com/x").content == b"ok"
        finally:
            client.close()
    finally:
        _crash(holder)
