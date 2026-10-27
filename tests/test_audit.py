"""Catalog audit: every verdict kind, exit codes and the evidence rule for `unsupported`."""

import json

import httpx
import pytest
import respx
from click.testing import CliRunner

from baseballpy.audit import (
    AuditFinding,
    Kind,
    audit_mlb,
    audit_savant,
    unsupported_without_evidence,
)
from baseballpy.cli import main
from baseballpy.core.config import RateLimitConfig
from baseballpy.core.http import HttpClient
from baseballpy.sources.mlb_api.endpoints import ROSTER_TYPES, STANDINGS_TYPES
from baseballpy.sources.mlb_api.schemas import GameType
from baseballpy.sources.statcast.lb_catalog import LEADERBOARDS, SAVANT_BASE

API = "https://statsapi.mlb.com/api/v1"


@pytest.fixture
def http() -> HttpClient:
    client = HttpClient(
        RateLimitConfig(
            host_rates={"statsapi.mlb.com": 1000.0, "baseballsavant.mlb.com": 1000.0},
            default_requests_per_second=1000.0,
            backoff_factor=0.01,
        ),
        http2=False,
    )
    yield client
    client.close()


def _provider_lists(**overrides: list[dict[str, object]]) -> None:
    lists: dict[str, list[dict[str, object]]] = {
        "standingsTypes": [{"name": n} for n in STANDINGS_TYPES],
        "rosterTypes": [{"parameter": n} for n in ROSTER_TYPES],
        "gameTypes": [{"id": m.value} for m in GameType],
        "statTypes": [{"displayName": "season"}],
        "statGroups": [{"displayName": "hitting"}],
    }
    lists.update(overrides)
    for name, rows in lists.items():
        respx.get(f"{API}/{name}").mock(return_value=httpx.Response(200, json=rows))


@respx.mock
def test_matching_provider_lists_produce_only_no_data_noise(http: HttpClient) -> None:
    _provider_lists(statTypes=[{"displayName": "season"}, {"displayName": "vsPlayer"}])
    findings = audit_mlb(http)
    assert [(f.kind, f.item) for f in findings] == [(Kind.NO_DATA, "stat type: vsPlayer")]
    assert not any(f.fails for f in findings)


@respx.mock
def test_missing_and_stale_items_are_reported_and_fail(http: HttpClient) -> None:
    _provider_lists(
        rosterTypes=[{"parameter": n} for n in (*ROSTER_TYPES, "brandNewRoster")][1:],
        gameTypes=[{"id": "R"}, {"id": "Z"}],
    )
    findings = audit_mlb(http)
    kinds = {(f.kind, f.item) for f in findings}
    assert (Kind.MISSING, "roster type: brandNewRoster") in kinds
    assert (Kind.STALE, f"roster type: {ROSTER_TYPES[0]}") in kinds
    assert (Kind.MISSING, "game type: Z") in kinds
    assert any(f.kind is Kind.STALE and f.item.startswith("game type") for f in findings)
    assert all(f.fails for f in findings if f.kind is Kind.MISSING)


@respx.mock
def test_an_unreadable_provider_list_is_an_error_not_silence(http: HttpClient) -> None:
    _provider_lists()
    respx.get(f"{API}/standingsTypes").mock(return_value=httpx.Response(200, json={"oops": 1}))
    findings = audit_mlb(http)
    assert any(f.kind is Kind.ERROR and f.fails for f in findings)


@respx.mock
def test_unsupported_leaderboard_that_answers_is_revived(http: HttpClient) -> None:
    unsupported = [d for d in LEADERBOARDS if d.unsupported is not None]
    assert unsupported, "the registry keeps documented unsupported routes"
    revived, dead = unsupported[0], unsupported[1:]
    respx.get(f"{SAVANT_BASE}/{revived.route}").mock(
        return_value=httpx.Response(200, content=b'"player_id","x"\n1,2\n3,4\n')
    )
    for defn in dead:
        respx.get(f"{SAVANT_BASE}/{defn.route}").mock(
            return_value=httpx.Response(200, content=b"<html>not a csv</html>")
        )
    findings = audit_savant(http)
    assert [(f.kind, f.item) for f in findings] == [(Kind.REVIVED, revived.slug)]
    assert findings[0].fails and "2 CSV rows" in findings[0].evidence


@respx.mock
def test_embedded_data_array_counts_as_revived(http: HttpClient) -> None:
    unsupported = [d for d in LEADERBOARDS if d.unsupported is not None]
    page = b'<html><script>const data = [{"a": 1}];</script></html>'
    for defn in unsupported:
        respx.get(f"{SAVANT_BASE}/{defn.route}").mock(
            return_value=httpx.Response(200, content=page)
        )
    findings = audit_savant(http)
    assert {f.item for f in findings} == {d.slug for d in unsupported}
    assert all("embeds a data array" in f.evidence for f in findings)


def test_every_unsupported_entry_records_when_and_what_was_tried() -> None:
    assert unsupported_without_evidence() == []
    for defn in LEADERBOARDS:
        if defn.unsupported is not None:
            assert defn.verified_on and defn.tried, defn.slug


def test_finding_failure_rules() -> None:
    assert AuditFinding(Kind.MISSING, "s", "i", "e").fails
    assert AuditFinding(Kind.REVIVED, "s", "i", "e").fails
    assert AuditFinding(Kind.ERROR, "s", "i", "e").fails
    assert not AuditFinding(Kind.STALE, "s", "i", "e").fails
    assert not AuditFinding(Kind.NO_DATA, "s", "i", "e").fails


@respx.mock
def test_cli_exit_code_and_json(http: HttpClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from baseballpy.core import http as http_mod

    monkeypatch.setattr(http_mod, "get_http_client", lambda: http)
    _provider_lists(gameTypes=[{"id": m.value} for m in GameType] + [{"id": "Q"}])
    respx.get(url__regex=rf"{SAVANT_BASE}/.*").mock(
        return_value=httpx.Response(200, content=b"<html>x</html>")
    )
    result = CliRunner().invoke(main, ["catalog", "audit", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert {
        "kind": "MISSING",
        "source": "mlb_api",
        "item": "game type: Q",
        "evidence": "/v1/gameTypes",
    } in payload
    clean = CliRunner().invoke(main, ["catalog", "audit", "--source", "statcast", "--json"])
    assert clean.exit_code == 0 and json.loads(clean.output) == []
