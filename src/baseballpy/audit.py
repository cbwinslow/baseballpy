"""Catalog completeness audit: provider-listed items vs what the registry covers.

``baseballpy catalog audit`` re-reads the providers' own lists (cheap, one request per list) and
reports what the registry is missing, what it carries that the provider no longer lists, which
``unsupported`` verdicts have come back to life, and which provider options have no data in the
generated combinations. A verdict of ``unsupported`` is a claim with an expiry date.
"""

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from baseballpy.core.http import HttpClient, HttpStatusError, TransportError
from baseballpy.sources.mlb_api.endpoints import (
    ENDPOINTS,
    ROSTER_TYPES,
    STANDINGS_TYPES,
)
from baseballpy.sources.mlb_api.schemas import GameType
from baseballpy.sources.mlb_api.stat_combos import (
    PEOPLE_STAT_COMBOS,
    PLAYER_STAT_COMBOS,
    TEAM_STAT_COMBOS,
)
from baseballpy.sources.statcast.lb_catalog import (
    LEADERBOARDS,
    SAVANT_BASE,
    request_params,
)
from baseballpy.sources.statcast.lb_parse import html_json_to_csv

MLB_API = "https://statsapi.mlb.com/api/v1"


class Kind(StrEnum):
    """Audit verdict kinds. MISSING and REVIVED make the audit fail."""

    MISSING = "MISSING"  # the provider lists it, the registry lacks it
    STALE = "STALE"  # the registry carries it, the provider no longer lists it
    REVIVED = "REVIVED"  # an `unsupported` item now returns data
    NO_DATA = "NO_DATA"  # listed by the provider, but no generated combination returned data
    ERROR = "ERROR"  # the provider list itself could not be read


@dataclass(frozen=True)
class AuditFinding:
    """One audit result with the evidence behind it."""

    kind: Kind
    source: str
    item: str
    evidence: str

    @property
    def fails(self) -> bool:
        """MISSING, REVIVED and ERROR findings fail the audit (exit code 1)."""
        return self.kind in (Kind.MISSING, Kind.REVIVED, Kind.ERROR)


def _list(http: HttpClient, path: str, key: str | None = None) -> list[dict[str, Any]] | None:
    try:
        result = http.get_sync(f"{MLB_API}/{path}", allow=(200,))
        data = json.loads(result.content)
    except (HttpStatusError, TransportError, ValueError):
        return None
    rows = data.get(key) if key and isinstance(data, dict) else data
    return rows if isinstance(rows, list) else None


def _diff(
    source: str,
    label: str,
    provider: set[str],
    registered: set[str],
    evidence: str,
) -> list[AuditFinding]:
    out = [
        AuditFinding(Kind.MISSING, source, f"{label}: {item}", evidence)
        for item in sorted(provider - registered)
    ]
    out += [
        AuditFinding(
            Kind.STALE, source, f"{label}: {item}", "registered but not listed by provider"
        )
        for item in sorted(registered - provider)
    ]
    return out


def audit_mlb(http: HttpClient) -> list[AuditFinding]:
    """Compare the MLB Stats API's own lists with the registry and the enums."""
    findings: list[AuditFinding] = []
    source = "mlb_api"

    def provider(path: str, field: str) -> set[str] | None:
        rows = _list(http, path)
        if rows is None:
            findings.append(
                AuditFinding(Kind.ERROR, source, path, f"GET /v1/{path} did not return a list")
            )
            return None
        return {str(r[field]) for r in rows if field in r}

    if (standings := provider("standingsTypes", "name")) is not None:
        findings += _diff(
            source, "standings type", standings, set(STANDINGS_TYPES), "/v1/standingsTypes"
        )
    if (rosters := provider("rosterTypes", "parameter")) is not None:
        findings += _diff(source, "roster type", rosters, set(ROSTER_TYPES), "/v1/rosterTypes")
    if (game_types := provider("gameTypes", "id")) is not None:
        findings += _diff(
            source, "game type", game_types, {member.value for member in GameType}, "/v1/gameTypes"
        )
    used_types = {s for s, _, _ in (*PLAYER_STAT_COMBOS, *TEAM_STAT_COMBOS, *PEOPLE_STAT_COMBOS)}
    used_groups = {g for _, g, _ in (*PLAYER_STAT_COMBOS, *TEAM_STAT_COMBOS, *PEOPLE_STAT_COMBOS)}
    if (stat_types := provider("statTypes", "displayName")) is not None:
        findings += [
            AuditFinding(
                Kind.NO_DATA, source, f"stat type: {t}", "no stat combination returned data"
            )
            for t in sorted(stat_types - used_types)
        ]
    if (groups := provider("statGroups", "displayName")) is not None:
        findings += [
            AuditFinding(
                Kind.NO_DATA, source, f"stat group: {g}", "no stat combination returned data"
            )
            for g in sorted(groups - used_groups)
        ]
    return findings


def audit_savant(http: HttpClient, year: int = 2024) -> list[AuditFinding]:
    """Re-probe every `unsupported` Savant leaderboard once; report the ones that now answer."""
    findings: list[AuditFinding] = []
    for defn in LEADERBOARDS:
        if defn.unsupported is None:
            continue
        url = f"{SAVANT_BASE}/{defn.route}"
        try:
            result = http.get_sync(url, params=request_params(defn, year, "0"), allow=(200,))
        except (HttpStatusError, TransportError):
            continue
        head = result.content[:200].lstrip()
        if not head.startswith(b"<") and b"," in result.content.split(b"\n", 1)[0]:
            rows = max(result.content.count(b"\n") - 1, 0)
            if rows > 0:
                findings.append(
                    AuditFinding(
                        Kind.REVIVED, "statcast", defn.slug, f"GET {url} returned {rows} CSV rows"
                    )
                )
                continue
        try:
            html_json_to_csv(result.content, defn.html_var)
        except ValueError:
            continue
        findings.append(
            AuditFinding(Kind.REVIVED, "statcast", defn.slug, f"GET {url} embeds a data array")
        )
    return findings


def unsupported_without_evidence() -> list[AuditFinding]:
    """Registry entries marked `unsupported` that do not record when they were verified."""
    out: list[AuditFinding] = []
    for ep in ENDPOINTS:
        if ep.unsupported is not None and ep.verified_on is None:
            out.append(
                AuditFinding(Kind.MISSING, "mlb_api", ep.name, "unsupported without verified_on")
            )
    for defn in LEADERBOARDS:
        if defn.unsupported is not None and defn.verified_on is None:
            out.append(
                AuditFinding(Kind.MISSING, "statcast", defn.slug, "unsupported without verified_on")
            )
    return out


def run_audit(
    http: HttpClient, sources: tuple[str, ...] = ("mlb_api", "statcast")
) -> list[AuditFinding]:
    """Run the audits of the requested sources plus the evidence-hygiene check."""
    findings: list[AuditFinding] = []
    if "mlb_api" in sources:
        findings += audit_mlb(http)
    if "statcast" in sources:
        findings += audit_savant(http)
    findings += unsupported_without_evidence()
    return findings
