"""``baseballpy probe``: a ten-second check of every provider route the project depends on.

A provider problem (the league-wide ``/v1/stats`` answering HTTP 406 for days, a 403 for a user
agent) is found here in seconds, before a long ingest starts and fails hours in. Each canary is one
small request; the table says which route answered what and, for a route with a known fallback,
what the code does instead. Exit code 1 when a canary fails.
"""

from dataclasses import dataclass
from datetime import date

import click
from rich.console import Console
from rich.table import Table

from baseballpy.core.config import LakeConfig
from baseballpy.core.http import HttpClient, HttpStatusError, TransportError

STATSAPI = "https://statsapi.mlb.com/api"
SAVANT = "https://baseballsavant.mlb.com"
#: a final game used to probe the live feed (any final game does)
CANARY_GAME_PK = 745000
CANARY_PERSON = 592450


@dataclass(frozen=True)
class Canary:
    """One small request and what to say when it fails."""

    name: str
    url: str
    params: dict[str, str]
    #: what the code does when this route is down (empty = nothing helps)
    fallback: str = ""


def canaries(season: int) -> list[Canary]:
    """The canary requests for ``season`` (a completed season; nothing is hard-coded)."""
    day = date(season, 6, 1).isoformat()
    stats = {"stats": "season", "group": "hitting", "season": str(season)}
    return [
        Canary("statsapi teams", f"{STATSAPI}/v1/teams", {"sportId": "1"}),
        Canary(
            "statsapi team stats",
            f"{STATSAPI}/v1/teams/stats",
            {**stats, "sportIds": "1"},
        ),
        Canary("statsapi person stats", f"{STATSAPI}/v1/people/{CANARY_PERSON}/stats", stats),
        Canary(
            "statsapi league-wide pool (/v1/stats)",
            f"{STATSAPI}/v1/stats",
            {**stats, "sportIds": "1", "playerPool": "ALL", "limit": "1"},
            fallback="players are fetched in batches through /v1/people?hydrate=stats(...)",
        ),
        Canary(
            "statsapi people hydrate",
            f"{STATSAPI}/v1/people",
            {
                "personIds": str(CANARY_PERSON),
                "hydrate": f"stats(group=[hitting],type=[season],season={season})",
            },
        ),
        Canary(
            "statsapi leaders",
            f"{STATSAPI}/v1/stats/leaders",
            {"leaderCategories": "homeRuns", "season": str(season)},
        ),
        Canary("statsapi schedule", f"{STATSAPI}/v1/schedule", {"sportId": "1", "date": day}),
        Canary("statsapi live feed", f"{STATSAPI}/v1.1/game/{CANARY_GAME_PK}/feed/live", {}),
        Canary(
            "savant leaderboard",
            f"{SAVANT}/leaderboard/sprint_speed",
            {"year": str(season), "min": "10", "csv": "true"},
        ),
        Canary(
            "savant pitch search (one day)",
            f"{SAVANT}/statcast_search/csv",
            {"all": "true", "type": "details", "game_date_gt": day, "game_date_lt": day},
        ),
        Canary("savant data dictionary", f"{SAVANT}/csv-docs", {}),
    ]


@dataclass(frozen=True)
class ProbeResult:
    """What one canary answered."""

    canary: Canary
    status: int | None
    seconds: float
    error: str = ""

    @property
    def ok(self) -> bool:
        """True for an HTTP 200."""
        return self.status == 200


def run_probe(http: HttpClient, season: int) -> list[ProbeResult]:
    """Send every canary once; errors become results, never exceptions."""
    results: list[ProbeResult] = []
    for canary in canaries(season):
        try:
            answer = http.get_sync(
                canary.url, params=canary.params, allow=tuple(range(200, 600)), timeout=30.0
            )
            results.append(ProbeResult(canary, answer.status, answer.elapsed_seconds))
        except (HttpStatusError, TransportError) as exc:
            results.append(ProbeResult(canary, None, 0.0, f"{type(exc).__name__}: {exc}"))
    return results


@click.command("probe")
@click.option("--season", type=int, default=None, help="Season to probe (default: last year).")
@click.pass_context
def probe_cmd(ctx: click.Context, season: int | None) -> None:
    """Check every provider route in seconds (run it before a long ingest)."""
    config = LakeConfig()
    year = season if season is not None else config.today_or_now().year - 1
    results = run_probe(HttpClient(), year)
    table = Table(title=f"Provider probe (season {year})")
    for column in ("Route", "Status", "Seconds", "Verdict"):
        table.add_column(column)
    failed = 0
    for result in results:
        if result.ok:
            verdict = "[green]ok[/green]"
        else:
            failed += 1
            note = result.canary.fallback
            verdict = "[red]FAILED[/red]" + (f" (fallback: {note})" if note else "")
            if result.error:
                verdict += f" {result.error}"
        table.add_row(
            result.canary.name,
            str(result.status) if result.status is not None else "-",
            f"{result.seconds:.1f}",
            verdict,
        )
    Console().print(table)
    ctx.exit(1 if failed else 0)


__all__ = ["Canary", "ProbeResult", "canaries", "probe_cmd", "run_probe"]
