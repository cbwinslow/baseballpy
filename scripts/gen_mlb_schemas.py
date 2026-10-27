"""Probe every declarative MLB endpoint live; generate strict schemas, stat combos and fixtures.

Usage::

    uv run python scripts/gen_mlb_schemas.py [--only NAME ...] [--skip-combos] [--check]

Phase 1 (unless ``--skip-combos``) enumerates ``/v1/statTypes`` x the stat groups and keeps the
combinations that return league-wide splits (written to ``stat_combos.py``, with the smallest column
set that makes the rows unique). Phase 2 requests a sample of every supported endpoint through the
shared ``HttpClient``, flattens the records, widens types across all sampled values and writes
``mlb_tables.py``, ``docs/mlb_probe.json`` and one trimmed fixture per endpoint under
``tests/fixtures/mlb/``.
"""

import argparse
import importlib
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from baseballpy.core.config import RateLimitConfig
from baseballpy.core.http import HttpClient, HttpStatusError, TransportError
from baseballpy.core.schema_tools import snake
from baseballpy.sources.mlb_api.flatten import Scalar, infer_type, iter_records, trim_payload

BASE = "https://statsapi.mlb.com/api/"


def stat_groups(http: HttpClient) -> list[str]:
    """Every stat group the provider lists (``/v1/statGroups``): nothing is skipped by choice."""
    groups = [g["displayName"] for g in get_json(http, "v1/statGroups", {}) or []]
    if not groups:
        raise SystemExit("/v1/statGroups returned nothing; refusing to probe a guessed list")
    return groups


KEY_CANDIDATES = (
    "person_id",
    "metric",
    "opposing_team_id",
    "opposing_player_id",
    "player.id",
    "team.id",
    "sport.id",
    "league.id",
    "season",
    "gameType",
    "split.code",
    "split.description",
    "date",
    "month",
    "dayOfWeek",
    "opponent.id",
    "game.gamePk",
    "position.abbreviation",
    "stat.pitchType.code",
    "stat.zone",
    "numTeams",
    "rank",
)
SAMPLE_SEASONS = (2024, 2015)
#: extra seasons for endpoints that are empty in the sample seasons but have data elsewhere
EXTRA_SEASONS = {
    "standings_first_half": (1981, 1994, 2020),
    "standings_second_half": (1981, 1994, 2020),
    "standings_postseason": (2020, 2008, 1995),
}
SAMPLE_TEAMS = (147, 119)
SAMPLE_GAMES = (745000, 775296)
SAMPLE_PEOPLE = tuple(
    (pid, "")
    for pid in (
        660271,  # Ohtani: two-way
        543037,  # Cole: starter
        592450,  # Judge
        605141,  # Betts
        477132,  # Kershaw
        521692,  # S. Perez: catcher
        623352,  # Hader: reliever
        545361,  # Trout: multi-year career
        518692,  # Freeman
        665742,  # Soto
    )
)
SAMPLE_AWARDS = ("MLBHOF", "ALMVP", "NLCY", "ALROY", "WSMVP", "ALPNT", "ALGG")
SAMPLE_SINCE = "2024-06-24T00:00:00Z"
FIXTURE_KEEP = 3
REF_FIXTURE_KEEP = 100  # reference lists are small; enum tests need them complete
FIXTURES = Path("tests/fixtures/mlb")


def get_json(http: HttpClient, path: str, params: dict[str, Any]) -> Any | None:
    """Parsed JSON of a 200 response, else ``None`` (never raises on 4xx/5xx)."""
    try:
        res = http.get_sync(BASE + path, params=params, allow=(200, 400, 404, 500, 503))
    except (HttpStatusError, TransportError):
        return None
    if res.status != 200:
        return None
    try:
        return json.loads(res.content)
    except ValueError:
        return None


def minimal_key(records: list[dict[str, Scalar]]) -> tuple[str, ...]:
    """Smallest set of always-populated columns that makes the rows unique.

    Tries the preferred ``KEY_CANDIDATES`` prefix first, then greedily adds the populated scalar
    column that separates the most rows; returns ``()`` only when no combination works.
    """
    if not records:
        return ()
    populated = [
        k
        for k in dict.fromkeys(k for r in records for k in r)
        if all(r.get(k) is not None for r in records)
        and all(not (isinstance(r.get(k), str) and len(str(r.get(k))) > 80) for r in records)
    ]

    def unique(cols: list[str]) -> bool:
        return len({tuple(r.get(c) for c in cols) for r in records}) == len(records)

    preferred = [c for c in KEY_CANDIDATES if c in populated]
    for size in range(1, len(preferred) + 1):
        if unique(preferred[:size]):
            return tuple(preferred[:size])
    chosen = list(preferred)
    while not unique(chosen) and len(chosen) < 8:
        rest = [c for c in populated if c not in chosen]
        if not rest:
            return ()
        chosen.append(
            max(rest, key=lambda c: len({tuple(r.get(x) for x in [*chosen, c]) for r in records}))
        )
    return tuple(chosen) if unique(chosen) else ()


def probe_combos(http: HttpClient, groups: list[str]) -> tuple[list[Any], list[Any]]:
    """Stat type x group combinations that return league-wide splits, with their keys."""
    stat_types = [t["displayName"] for t in get_json(http, "v1/statTypes", {}) or []]
    players: list[Any] = []
    teams: list[Any] = []
    for stat in stat_types:
        for group in groups:
            for label, path, out, extra in (
                ("player", "v1/stats", players, {"playerPool": "ALL", "limit": 400}),
                ("team", "v1/teams/stats", teams, {}),
            ):
                data = get_json(
                    http,
                    path,
                    {"stats": stat, "group": group, "season": 2024, "sportIds": 1, **extra},
                )
                records = list(iter_records(data, ("stats", "*", "splits"))) if data else []
                if records:
                    out.append((stat, group, minimal_key(records)))
                    print(
                        f"  {label:6s} {stat:24s} {group:9s} {len(records):5d} rows key={out[-1][2]}"
                    )
    return players, teams


def probe_people_combos(http: HttpClient, groups: list[str]) -> list[Any]:
    """Stat type x group combinations that return splits for the sample people."""
    stat_types = [t["displayName"] for t in get_json(http, "v1/statTypes", {}) or []]
    combos: dict[tuple[str, str], list[dict[str, Scalar]]] = {}
    for stat in stat_types:
        for group in groups:
            for pid, _ in SAMPLE_PEOPLE:
                data = get_json(
                    http, f"v1/people/{pid}/stats", {"stats": stat, "group": group, "season": 2024}
                )
                records = list(iter_records(data, ("stats", "*", "splits"))) if data else []
                if records:
                    combos.setdefault((stat, group), []).extend(
                        {**r, "person_id": pid} for r in records
                    )
    out = []
    for (stat, group), records in combos.items():
        out.append((stat, group, minimal_key(records)))
        print(f"  person {stat:24s} {group:9s} {len(records):5d} rows key={out[-1][2]}")
    return out


def probe_param_combos(
    http: HttpClient, groups: list[str], productive: set[str]
) -> tuple[list[Any], list[Any]]:
    """Probe the stat types that returned nothing with their documented parameters.

    Protocol (ADR 37): the bare request already failed; try, one at a time, ``sitCodes`` (every
    situation code in one request), the season-less form, an opposing player/team and, for
    metric/tracking types, ``metrics``. Returns (combinations, unsupported with evidence).
    """
    stat_types = [t["displayName"] for t in get_json(http, "v1/statTypes", {}) or []]
    codes = [c["code"] for c in get_json(http, "v1/situationCodes", {}) or []]
    metrics = [m["name"] for m in get_json(http, "v1/metrics", {}) or [] if m.get("name")]
    people = [p for p, _ in SAMPLE_PEOPLE[:4]]
    found: list[Any] = []
    unsupported: list[Any] = []
    for stat in stat_types:
        if stat in productive:
            continue
        variants: list[tuple[str, tuple[tuple[str, str], ...], list[dict[str, Any]]]] = [
            (
                "sit",
                (("season", "{season}"), ("sitCodes", "{sit_codes}")),
                [{"season": 2024, "sitCodes": ",".join(codes)}],
            ),
            ("no_season", (), [{}]),
            (
                "opposing_player",
                (("season", "{season}"), ("opposingPlayerId", "{opposing_player_id}")),
                [
                    {
                        "season": 2024,
                        "opposingPlayerId": 543037,
                        "_dim": ("opposing_player_id", 543037),
                    }
                ],
            ),
            (
                "opposing_team",
                (("season", "{season}"), ("opposingTeamId", "{opposing_team_id}")),
                [{"season": 2024, "opposingTeamId": 147, "_dim": ("opposing_team_id", 147)}],
            ),
        ]
        if "metric" in stat.lower() or "tracking" in stat.lower():
            variants.append(
                (
                    "metric",
                    (("season", "{season}"), ("metrics", "{metric}")),
                    [{"season": 2024, "metrics": m, "_dim": ("metric", m)} for m in metrics],
                )
            )
        tried: list[str] = [f"bare request returned no splits for {len(groups)} groups"]
        hit = False
        for group in groups:
            for name, template, samples in variants:
                for scope in ("person", "league"):
                    if scope == "league" and name not in ("sit", "no_season"):
                        continue
                    records: list[dict[str, Scalar]] = []
                    for sample in samples:
                        params = {k: v for k, v in sample.items() if k != "_dim"}
                        extra = {sample["_dim"][0]: sample["_dim"][1]} if "_dim" in sample else {}
                        targets = people if scope == "person" else [None]
                        for pid in targets:
                            path = f"v1/people/{pid}/stats" if scope == "person" else "v1/stats"
                            query = {"stats": stat, "group": group, **params}
                            if scope == "league":
                                query.update({"sportIds": 1, "playerPool": "ALL", "limit": 100})
                            data = get_json(http, path, query)
                            got = list(iter_records(data, ("stats", "*", "splits"))) if data else []
                            records.extend(
                                {**({"person_id": pid} if pid else {}), **extra, **r} for r in got
                            )
                        if (
                            records
                            and name == "metric"
                            and len({r.get("metric") for r in records}) >= 3
                        ):
                            break
                    if records:
                        hit = True
                        key = minimal_key(records) or (
                            ("person_id",) if scope == "person" else ("season",)
                        )
                        found.append((scope, stat, group, template, key))
                        print(
                            f"  param {scope:6s} {stat:20s} {group:9s} {name:16s} {len(records):6d} rows key={key}"
                        )
            tried.append(
                f"{group}: sit/no_season/opposing"
                + ("/metrics" if "metric" in stat.lower() or "tracking" in stat.lower() else "")
                + " variants returned nothing"
            )
        if not hit:
            unsupported.append((stat, date.today().isoformat(), tuple(tried[:2])))
            print(f"  param {stat}: NO DATA after the protocol")
    return found, unsupported


def write_combos(
    players: list[Any],
    teams: list[Any],
    people: list[Any],
    param: list[Any] | None = None,
    unsupported: list[Any] | None = None,
) -> None:
    """Write ``stat_combos.py``."""

    def render(rows: list[Any], fallback: tuple[str, ...]) -> str:
        body = "".join(f"    ({s!r}, {g!r}, {(k or fallback)!r}),\n" for s, g, k in rows)
        return f"(\n{body})" if rows else "()"

    Path("src/baseballpy/sources/mlb_api/stat_combos.py").write_text(
        '"""GENERATED by scripts/gen_mlb_schemas.py (stat type x group combinations that return data)."""\n\n'
        "#: (stat type, group, key columns) for ``/v1/stats`` (league-wide player pool)\n"
        f"PLAYER_STAT_COMBOS: tuple[tuple[str, str, tuple[str, ...]], ...] = {render(players, ('season',))}\n"
        "#: (stat type, group, key columns) for ``/v1/teams/stats``\n"
        f"TEAM_STAT_COMBOS: tuple[tuple[str, str, tuple[str, ...]], ...] = {render(teams, ('season',))}\n"
        "#: (stat type, group, key columns) for ``/v1/people/{id}/stats`` (per person)\n"
        f"PEOPLE_STAT_COMBOS: tuple[tuple[str, str, tuple[str, ...]], ...] = {render(people, ('person_id',))}\n"
        "#: parameterized combinations: (scope, stat type, group, extra params, key columns); scope is\n"
        "#: ``person`` (``/v1/people/{id}/stats``) or ``league`` (``/v1/stats``); ``{metric}``,\n"
        "#: ``{opposing_team_id}`` and ``{opposing_player_id}`` placeholders are fan-out dimensions\n"
        "PARAM_STAT_COMBOS: tuple[\n    tuple[str, str, str, tuple[tuple[str, str], ...], tuple[str, ...]], ...\n] = "
        + (repr(tuple(param)) if param else "()")
        + "\n#: stat types that stayed empty after the probe protocol: (stat type, verified on, what was tried)\n"
        "UNSUPPORTED_STAT_TYPES: tuple[tuple[str, str, tuple[str, ...]], ...] = "
        + (repr(tuple(unsupported)) if unsupported else "()")
        + "\n",
        encoding="utf-8",
    )


def sample_games(http: HttpClient) -> tuple[int, ...]:
    """Two fixed 2024 games plus the first game of 2015-06-15 (older-era shape)."""
    data = get_json(http, "v1/schedule", {"sportId": 1, "date": "2015-06-15"})
    older = [g["gamePk"] for g in next(iter_games(data), [])] if data else []
    return (*SAMPLE_GAMES, *older[:1])


def iter_games(data: Any) -> Any:
    """Yield the game list of each schedule date."""
    for day in data.get("dates", []):
        yield day.get("games", [])


def profile(http: HttpClient, ep: Any, ctxs: list[Any], requests_for: Any) -> dict[str, Any]:
    """Fetch the sample requests of an endpoint and pool the flattened records."""
    records: list[dict[str, Scalar]] = []
    fixture: Any = None
    ok = errors = 0
    seen: set[str] = set()
    per_request: list[list[dict[str, Scalar]]] = []
    for ctx in ctxs:
        try:
            requests = list(requests_for(ep, ctx))
        except ValueError:
            continue
        for request in requests:
            params = dict(request.params)
            fingerprint = request.path + json.dumps(params, sort_keys=True)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            if ep.paginated:
                params["limit"] = 50
            data = get_json(http, request.path, params)
            if data is None:
                errors += 1
                continue
            got = [{**request.extra, **r} for r in iter_records(data, ep.records)]
            per_request.append(got)
            ok += 1
            if got and fixture is None:
                keep = REF_FIXTURE_KEEP if ep.name.startswith("ref_") else FIXTURE_KEEP
                fixture = trim_payload(data, ep.records, keep)
            records.extend(got)
    return {
        "records": records,
        "fixture": fixture,
        "ok": ok,
        "errors": errors,
        "per_request": per_request,
    }


def columns_of(records: list[dict[str, Scalar]]) -> list[tuple[str, str, str]]:
    """``(column, type, upstream)`` for the pooled records, in first-seen order."""
    order: list[str] = []
    for r in records:
        for k in r:
            if k not in order:
                order.append(k)
    out: list[tuple[str, str, str]] = []
    used: set[str] = set()
    for key in order:
        name = snake(key) or "col"
        base, n = name, 1
        while name in used:
            n += 1
            name = f"{base}_{n}"
        used.add(name)
        out.append((name, infer_type(r.get(key) for r in records) or "string", key))
    return out


def render_tables(tables: dict[str, list[tuple[str, str, str]]]) -> str:
    """Text of the generated ``mlb_tables.py``."""
    lines = [
        '"""GENERATED by scripts/gen_mlb_schemas.py from live responses. Do not edit."""',
        "",
        "MLB_COLUMNS: dict[str, tuple[tuple[str, str, str], ...]] = {",
    ]
    for name, cols in tables.items():
        lines.append(f'    "{name}": (')
        lines.extend(f'        ("{c}", "{t}", {json.dumps(u)}),' for c, t, u in cols)
        lines.append("    ),")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--skip-combos", action="store_true")
    parser.add_argument("--check", action="store_true", help="probe only, write nothing")
    args = parser.parse_args()
    http = HttpClient(RateLimitConfig())
    if not args.skip_combos and not args.only:
        print("phase 1: stat combos")
        groups = stat_groups(http)
        print(f"  stat groups: {groups}")
        players, teams = probe_combos(http, groups)
        people = probe_people_combos(http, groups)
        productive = {c[0] for c in (*players, *teams, *people)}
        param, unsupported_stats = probe_param_combos(http, groups, productive)
        if not args.check:
            write_combos(players, teams, people, param, unsupported_stats)
        print(f"  {len(players)} player, {len(teams)} team, {len(people)} person combos")
    # endpoints are built from stat_combos.py, so import them only after phase 1
    import baseballpy.sources.mlb_api.endpoints as endpoints_mod
    import baseballpy.sources.mlb_api.stat_combos as combos_mod

    importlib.reload(combos_mod)
    importlib.reload(endpoints_mod)
    from baseballpy.sources.mlb_api.endpoints import ENDPOINTS, Context, requests_for

    EXTRA_CTX = {
        "person_ids": tuple(p for p, _ in SAMPLE_PEOPLE),
        "award_ids": SAMPLE_AWARDS,
        "updated_since": SAMPLE_SINCE,
        "query": "Judge",
        "sit_codes": tuple(c["code"] for c in get_json(http, "v1/situationCodes", {}) or []),
        "metrics": tuple(
            m["name"] for m in get_json(http, "v1/metrics", {}) or [] if m.get("name")
        )[:4],
        "opposing_team_ids": (147, 119),
        "opposing_player_ids": (543037, 592450),
    }
    leaders = [t["displayName"] for t in get_json(http, "v1/leagueLeaderTypes", {}) or []]
    games = sample_games(http)
    ctxs = [
        Context(
            season=season,
            sport_ids=(1,),
            team_ids=SAMPLE_TEAMS if season == SAMPLE_SEASONS[0] else (),
            game_pks=games,
            leader_categories=leaders,
            **EXTRA_CTX,
        )
        for season in SAMPLE_SEASONS
    ]
    ctxs[0] = Context(
        season=SAMPLE_SEASONS[0],
        sport_ids=(1,),
        team_ids=SAMPLE_TEAMS,
        game_pks=games,
        leader_categories=leaders,
        **EXTRA_CTX,
    )
    all_teams = tuple(
        t["id"]
        for t in (get_json(http, "v1/teams", {"sportId": 1, "season": 2024}) or {}).get("teams", [])
    )
    ctxs.append(
        Context(
            season=2024,
            sport_ids=(1,),
            team_ids=all_teams,
            game_pks=games,
            leader_categories=leaders,
            **EXTRA_CTX,
        )
    )
    tables: dict[str, list[tuple[str, str, str]]] = {}
    probe: dict[str, Any] = {}
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for ep in ENDPOINTS:
        if args.only and ep.name not in args.only:
            continue
        if ep.unsupported is not None:
            probe[ep.name] = {"status": "unsupported", "reason": ep.unsupported}
            continue
        started = time.perf_counter()
        use = ctxs if ep.scope != "teams_season" else [ctxs[-1]]
        for year in EXTRA_SEASONS.get(ep.name, ()):
            use = [*use, Context(season=year, sport_ids=(1,), **EXTRA_CTX)]
        result = profile(http, ep, use, requests_for)
        records = result["records"]
        status = "ok" if records else "empty"
        key_ok = None
        if records and ep.keys:
            cols = [snake(k) for k in ep.keys]
            lookup = {snake(k): k for r in records[:1] for k in r}
            keys = [lookup.get(c, c) for c in cols]
            key_ok = all(
                len({tuple(r.get(k) for k in keys) for r in chunk}) == len(chunk)
                for chunk in result["per_request"]
            )
        probe[ep.name] = {
            "status": status,
            "requests_ok": result["ok"],
            "requests_failed": result["errors"],
            "sample_rows": len(records),
            "columns": len(columns_of(records)) if records else 0,
            "key_unique_per_request": key_ok,
        }
        print(
            f"{ep.name:38s} {status:5s} rows={len(records):6d} req_ok={result['ok']:3d} "
            f"fail={result['errors']:3d} key_unique={key_ok} ({time.perf_counter() - started:.0f}s)",
            flush=True,
        )
        if records:
            tables[ep.name] = columns_of(records)
            if result["fixture"] is not None and not args.check:
                (FIXTURES / f"{ep.name}.json").write_text(
                    json.dumps(result["fixture"], indent=1, ensure_ascii=False), encoding="utf-8"
                )
    if not args.check:
        tables_path = Path("src/baseballpy/sources/mlb_api/mlb_tables.py")
        probe_path = Path("docs/mlb_probe.json")
        if args.only:  # merge into the existing generated files
            from baseballpy.sources.mlb_api.mlb_tables import MLB_COLUMNS

            tables = {**{k: list(v) for k, v in MLB_COLUMNS.items()}, **tables}
            old = json.loads(probe_path.read_text(encoding="utf-8"))["endpoints"]
            probe = {**old, **probe}
        tables_path.write_text(render_tables(tables), encoding="utf-8")
        probe_path.write_text(
            json.dumps({"probed_on": date.today().isoformat(), "endpoints": probe}, indent=1),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
