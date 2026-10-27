"""Declarative registry of MLB Stats API endpoints (one :class:`MlbEndpoint` per dataset).

An endpoint is data: a path/params template, the path of its record list inside the JSON, its
fan-out ``scope`` and its natural key. The generic extractor (:mod:`.generic`) turns any of them
into a typed Parquet dataset, using schemas generated from live responses (``mlb_tables.py``).
Routes that answer 4xx or carry no record list are kept with an ``unsupported`` reason.
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from baseballpy.core.schema_tools import snake
from baseballpy.sources.mlb_api.stat_combos import (
    PEOPLE_STAT_COMBOS,
    PLAYER_STAT_COMBOS,
    TEAM_STAT_COMBOS,
)

MLB_BASE_URL = "https://statsapi.mlb.com/api"

#: scope -> what one request is made for
SCOPES = (
    "flat",
    "season",
    "team_season",
    "teams_season",
    "game",
    "person_season",
    "award_season",
    "since",
    "query",
)
#: scopes whose chunks are stored under ``season=YYYY``
PARTITIONED_SCOPES = frozenset(
    {"season", "team_season", "teams_season", "game", "person_season", "award_season"}
)


@dataclass(frozen=True)
class MlbEndpoint:
    """One MLB Stats API dataset."""

    name: str
    path: str
    records: tuple[str, ...]
    description: str
    keys: tuple[str, ...]
    scope: str = "flat"
    params: Mapping[str, str | int] = field(default_factory=dict)
    #: freshness policy key (see ``core/freshness.py``); reference data is daily
    freshness: str = "reference"
    unsupported: str | None = None
    #: when the ``unsupported`` verdict was last verified and what was tried (evidence, not memory)
    verified_on: str | None = None
    tried: tuple[str, ...] = ()
    #: fetched in ``limit``/``offset`` pages (the total is ``stats[0].totalSplits``)
    paginated: bool = False
    #: a 404 for one request means "nothing there" (recorded as an empty part, counted in the report)
    tolerate_missing: bool = False

    @property
    def heavy(self) -> bool:
        """All-time stat types ignore the season (every player in history, minutes per request)."""
        return self.name.startswith(
            (
                "stats_career",
                "stats_year_by_year",
                "stats_stats_single_season",  # every player-season in history (192k rows)
                "team_stats_career",
                "team_stats_year_by_year",
            )
        )

    @property
    def partitioned(self) -> bool:
        """Season-partitioned scopes; ``flat``, ``since`` and ``query`` datasets are unpartitioned."""
        return self.scope in PARTITIONED_SCOPES


@dataclass(frozen=True)
class Context:
    """Fan-out values a request set is built from."""

    season: int | None = None
    sport_ids: Sequence[int] = (1,)
    team_ids: Sequence[int] = ()
    game_pks: Sequence[int] = ()
    leader_categories: Sequence[str] = ()
    person_ids: Sequence[int] = ()
    award_ids: Sequence[str] = ()
    updated_since: str | None = None
    query: str | None = None


@dataclass(frozen=True)
class Request:
    """One concrete request of an endpoint: its chunk id, path and query parameters."""

    ident: str
    path: str
    params: dict[str, str | int]
    season: int | None
    #: columns added to every record (the fan-out value the payload itself does not repeat)
    extra: Mapping[str, str | int] = field(default_factory=dict)


def _fill(template: str, values: Mapping[str, str | int]) -> str:
    try:
        return template.format(**values)
    except KeyError as exc:
        raise ValueError(f"endpoint template {template!r} needs {exc.args[0]!r}") from None


def requests_for(endpoint: MlbEndpoint, ctx: Context) -> Iterator[Request]:
    """The requests an endpoint needs for ``ctx`` (a fan-out per scope)."""
    base: dict[str, str | int] = {}
    values: dict[str, str | int]
    if ctx.season is not None:
        base["season"] = ctx.season
        base["year"] = ctx.season
    if endpoint.scope == "flat":
        yield Request(endpoint.name, endpoint.path, dict(endpoint.params), None)
        return
    if endpoint.scope in ("since", "query"):
        value = ctx.updated_since if endpoint.scope == "since" else ctx.query
        if value is None:
            raise ValueError(
                f"{endpoint.name} needs ctx.{'updated_since' if endpoint.scope == 'since' else 'query'}"
            )
        values = {"value": value}
        safe = "".join(c if c.isalnum() else "-" for c in value)
        yield Request(
            f"{endpoint.name}_{safe}",
            endpoint.path,
            {k: _fill(str(v), values) for k, v in endpoint.params.items()},
            None,
        )
        return
    if ctx.season is None and endpoint.scope not in ("game",):
        raise ValueError(f"{endpoint.name} is season-scoped; ctx.season is required")
    if endpoint.scope == "season":
        for sport in ctx.sport_ids:
            values = {
                **base,
                "sport_id": sport,
                "leader_categories": ",".join(ctx.leader_categories),
            }
            ident = f"{endpoint.name}_{ctx.season}" + (
                f"_sport{sport}" if "{sport_id}" in _all(endpoint) else ""
            )
            yield Request(
                ident,
                _fill(endpoint.path, values),
                {k: _fill(str(v), values) for k, v in endpoint.params.items()},
                ctx.season,
                {"sport_id": sport} if "{sport_id}" in _all(endpoint) else {},
            )
            if "{sport_id}" not in _all(endpoint):
                return
    elif endpoint.scope == "teams_season":
        values = {**base, "team_ids": ",".join(str(t) for t in ctx.team_ids)}
        yield Request(
            f"{endpoint.name}_{ctx.season}",
            _fill(endpoint.path, values),
            {k: _fill(str(v), values) for k, v in endpoint.params.items()},
            ctx.season,
        )
    elif endpoint.scope == "team_season":
        for team in ctx.team_ids:
            values = {**base, "team_id": team}
            yield Request(
                f"{endpoint.name}_{ctx.season}_{team}",
                _fill(endpoint.path, values),
                {k: _fill(str(v), values) for k, v in endpoint.params.items()},
                ctx.season,
                {"team_id": team},
            )
    elif endpoint.scope == "game":
        for pk in ctx.game_pks:
            values = {**base, "game_pk": pk}
            yield Request(
                f"{endpoint.name}_{pk}",
                _fill(endpoint.path, values),
                {k: _fill(str(v), values) for k, v in endpoint.params.items()},
                ctx.season,
                {"game_pk": pk},
            )
    elif endpoint.scope == "person_season":
        for person in ctx.person_ids:
            values = {**base, "person_id": person}
            yield Request(
                f"{endpoint.name}_{ctx.season}_{person}",
                _fill(endpoint.path, values),
                {k: _fill(str(v), values) for k, v in endpoint.params.items()},
                ctx.season,
                {"person_id": person},
            )
    elif endpoint.scope == "award_season":
        for award in ctx.award_ids:
            values = {**base, "award_id": award}
            yield Request(
                f"{endpoint.name}_{ctx.season}_{award}",
                _fill(endpoint.path, values),
                {k: _fill(str(v), values) for k, v in endpoint.params.items()},
                ctx.season,
                {"request_award_id": award},
            )
    else:
        raise ValueError(f"unknown scope {endpoint.scope!r} for {endpoint.name}")


def _all(endpoint: MlbEndpoint) -> str:
    return endpoint.path + " " + " ".join(str(v) for v in endpoint.params.values())


#: reference/meta lists: ``GET /v1/<route>``; dict-wrapped ones name their list key
_REFERENCE: tuple[tuple[str, tuple[str, ...], str, tuple[str, ...]], ...] = (
    ("gameTypes", (), "Game type codes (R, P, S, ...).", ("id",)),
    (
        "statTypes",
        (),
        "Stat type names usable in /v1/stats (season, career, gameLog, ...).",
        ("displayName",),
    ),
    ("statGroups", (), "Stat groups (hitting, pitching, fielding, ...).", ("displayName",)),
    ("leagueLeaderTypes", (), "League leader categories.", ("displayName",)),
    ("positions", (), "Fielding/lineup positions.", ("abbrev",)),
    ("rosterTypes", (), "Roster types (active, 40Man, fullSeason, ...).", ("parameter",)),
    ("standingsTypes", (), "Standings types (regularSeason, wildCard, ...).", ("name",)),
    ("pitchTypes", (), "Pitch type codes.", ("code",)),
    ("eventTypes", (), "Play event types.", ("code",)),
    ("hitTrajectories", (), "Batted-ball trajectories.", ("code",)),
    ("situationCodes", (), "Situation (split) codes.", ("code",)),
    ("scheduleEventTypes", (), "Schedule event types.", ("code",)),
    ("scheduleTypes", (), "Schedule types.", ("id",)),
    ("windDirection", (), "Wind direction codes.", ("code",)),
    ("languages", (), "Languages.", ("languageCode",)),
    ("platforms", (), "Platforms.", ("platformCode",)),
    ("reviewReasons", (), "Replay review reasons.", ("code",)),
    ("logicalEvents", (), "Logical event types.", ("code",)),
    ("metrics", (), "Tracking metrics.", ("name",)),
    (
        "baseballStats",
        (),
        "Statistic definitions (name, group, lookup param).",
        ("name", "statGroups"),
    ),
    ("gameStatus", (), "Game status codes.", ("statusCode",)),
    ("awards", ("awards",), "Award catalog.", ("id",)),
    ("jobTypes", (), "Job (role) types.", ("code",)),
    ("sports", ("sports",), "Sports / levels (MLB, AAA, ...).", ("id",)),
    ("league", ("leagues",), "All leagues.", ("id",)),
    ("divisions", ("divisions",), "All divisions.", ("id",)),
    ("conferences", ("conferences",), "All conferences.", ("id",)),
)


def _reference_endpoints() -> list[MlbEndpoint]:
    return [
        MlbEndpoint(
            name=f"ref_{snake(route)}",
            path=f"v1/{route}",
            records=records,
            description=desc,
            keys=keys,
        )
        for route, records, desc, keys in _REFERENCE
    ]


#: standings types accepted by ``standingsTypes=`` (from /v1/standingsTypes, probed 2026-10-27)
STANDINGS_TYPES = (
    "regularSeason",
    "wildCard",
    "divisionLeaders",
    "wildCardWithLeaders",
    "firstHalf",
    "secondHalf",
    "springTraining",
    "postseason",
    "byDivision",
    "byConference",
    "byLeague",
    "byOrganization",
    "currentHalf",
)

ROSTER_TYPES = (
    "active",
    "40Man",
    "fullSeason",
    "fullRoster",
    "nonRosterInvitees",
    "depthChart",
    "allTime",
    "coach",
    "gameday",
)


def _ep(
    name: str,
    path: str,
    records: tuple[str, ...],
    description: str,
    keys: tuple[str, ...],
    scope: str = "flat",
    tolerate_missing: bool = False,
    **params: str | int,
) -> MlbEndpoint:
    return MlbEndpoint(
        name, path, records, description, keys, scope, params, tolerate_missing=tolerate_missing
    )


_STANDINGS = [
    MlbEndpoint(
        f"standings_{snake(kind)}",
        "v1/standings",
        ("records", "*", "teamRecords"),
        f"Standings, type {kind}.",
        ("team.id", "records.standingsType"),
        "season",
        {"leagueId": "103,104", "season": "{season}", "standingsTypes": kind},
        "standings",
    )
    for kind in STANDINGS_TYPES
]

_ROSTERS = [
    MlbEndpoint(
        f"team_roster_{snake(kind)}",
        "v1/teams/{team_id}/roster",
        ("roster",),
        f"Team roster, type {kind}.",
        ("team_id", "person.id", "job")
        if kind == "coach"
        else ("team_id", "person.id", "position.code"),
        "team_season",
        {"rosterType": kind, "season": "{season}"},
        "roster",
    )
    for kind in ROSTER_TYPES
]

PAGE_SIZE = 1000

_STATS = [
    MlbEndpoint(
        f"stats_{snake(stat)}_{group}",
        "v1/stats",
        ("stats", "*", "splits"),
        f"League-wide {group} stats, type {stat} (player pool ALL).",
        keys,
        "season",
        {
            "stats": stat,
            "group": group,
            "season": "{season}",
            "sportIds": "{sport_id}",
            "playerPool": "ALL",
        },
        "stats",
        paginated=True,
    )
    for stat, group, keys in PLAYER_STAT_COMBOS
]
_TEAM_STATS = [
    MlbEndpoint(
        f"team_stats_{snake(stat)}_{group}",
        "v1/teams/stats",
        ("stats", "*", "splits"),
        f"Team {group} stats, type {stat}.",
        keys,
        "season",
        {"stats": stat, "group": group, "season": "{season}", "sportIds": "{sport_id}"},
        "stats",
    )
    for stat, group, keys in TEAM_STAT_COMBOS
]

_PEOPLE_STATS = [
    MlbEndpoint(
        f"people_stats_{snake(stat)}_{group}",
        "v1/people/{person_id}/stats",
        ("stats", "*", "splits"),
        f"Per-player {group} stats, type {stat} (one request per person).",
        keys,
        "person_season",
        {"stats": stat, "group": group, "season": "{season}"},
        "stats",
    )
    for stat, group, keys in PEOPLE_STAT_COMBOS
]

ENDPOINTS: tuple[MlbEndpoint, ...] = (
    *_STATS,
    *_PEOPLE_STATS,
    *_TEAM_STATS,
    *_reference_endpoints(),
    _ep(
        "seasons_all",
        "v1/seasons/all",
        ("seasons",),
        "Every season of a sport (calendar dates).",
        ("seasonId",),
        sportId=1,
    ),
    _ep(
        "teams_season",
        "v1/teams",
        ("teams",),
        "Teams of a season (sport 1 = MLB).",
        ("id",),
        "season",
        sportId="{sport_id}",
        season="{season}",
    ),
    _ep(
        "divisions_season",
        "v1/divisions",
        ("divisions",),
        "Divisions of a season.",
        ("id",),
        "season",
        sportId="{sport_id}",
        season="{season}",
    ),
    _ep(
        "leagues_season",
        "v1/league",
        ("leagues",),
        "Leagues of a season.",
        ("id",),
        "season",
        sportId="{sport_id}",
        seasons="{season}",
    ),
    _ep(
        "team_affiliates",
        "v1/teams/affiliates",
        ("teams",),
        "Minor-league affiliates of every MLB club.",
        ("id", "parentOrgId"),
        "teams_season",
        teamIds="{team_ids}",
        season="{season}",
    ),
    _ep(
        "team_history",
        "v1/teams/history",
        ("teams",),
        "Franchise history (names/locations by season).",
        ("id", "season"),
        teamIds="108,109,110,111,112,113,114,115,116,117,118,119,120,121,133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,158",
    ),
    _ep(
        "team_coaches",
        "v1/teams/{team_id}/coaches",
        ("roster",),
        "Coaching staff of a club-season.",
        ("team_id", "person.id", "job"),
        "team_season",
        season="{season}",
    ),
    _ep(
        "team_personnel",
        "v1/teams/{team_id}/personnel",
        ("roster",),
        "Non-playing personnel of a club-season.",
        ("team_id", "person.id", "job"),
        "team_season",
        season="{season}",
    ),
    _ep(
        "team_alumni",
        "v1/teams/{team_id}/alumni",
        ("people",),
        "Club alumni (hitting) of a season.",
        ("team_id", "id"),
        "team_season",
        season="{season}",
        group="hitting",
    ),
    *_ROSTERS,
    _ep(
        "players_season",
        "v1/sports/{sport_id}/players",
        ("people",),
        "Every player of a sport-season with biographical fields.",
        ("id",),
        "season",
        season="{season}",
    ),
    _ep(
        "free_agents",
        "v1/people/freeAgents",
        ("freeAgents",),
        "Free agents of a season.",
        ("player.id",),
        "season",
        season="{season}",
    ),
    _ep(
        "transactions_season",
        "v1/transactions",
        ("transactions",),
        "Every transaction of a calendar year (trades, signings, DFAs, IL moves, ...), all fields.",
        ("id",),
        "season",
        startDate="{season}-01-01",
        endDate="{season}-12-31",
    ),
    _ep(
        "draft_picks",
        "v1/draft/{year}",
        ("drafts", "rounds", "*", "picks"),
        "Every pick of a draft year with the person, school, scouting and signing fields.",
        ("pickNumber", "pickRound"),
        "season",
    ),
    _ep(
        "venues_hydrated",
        "v1/venues",
        ("venues",),
        "Every venue with location, field info, time zone and external ids hydrated.",
        ("id",),
        hydrate="location,fieldInfo,timezone,xrefId,social",
    ),
    _ep(
        "award_recipients",
        "v1/awards/{award_id}/recipients",
        ("awards",),
        "Recipients of every award for a season (one request per award id; several rows per award-season are normal).",
        ("id", "season"),
        "award_season",
        tolerate_missing=True,
        season="{season}",
    ),
    _ep(
        "people_changes",
        "v1/people/changes",
        ("people",),
        "People changed since a timestamp (incremental sync log; append-only).",
        ("id",),
        "since",
        updatedSince="{value}",
    ),
    _ep(
        "game_changes",
        "v1/game/changes",
        ("dates", "*", "games"),
        "Games changed since a timestamp (incremental sync log; append-only).",
        ("gamePk",),
        "since",
        updatedSince="{value}",
    ),
    _ep(
        "people_search",
        "v1/people/search",
        ("people",),
        "People matching a name query (on demand).",
        ("id",),
        "query",
        names="{value}",
    ),
    _ep("jobs_umpires", "v1/jobs/umpires", ("roster",), "Current umpire roster.", ("person.id",)),
    _ep(
        "jobs_datacasters",
        "v1/jobs/datacasters",
        ("roster",),
        "Current datacasters (the upstream listing repeats some people, so the key is not unique).",
        ("person.id",),
    ),
    _ep(
        "jobs_official_scorers",
        "v1/jobs/officialScorers",
        ("roster",),
        "Current official scorers (the upstream listing repeats some people, so the key is not unique).",
        ("person.id",),
    ),
    _ep(
        "draft_prospects",
        "v1/draft/prospects/{year}",
        ("prospects",),
        "Draft prospects of a year.",
        ("person.id", "bisPlayerId"),
        "season",
    ),
    _ep(
        "schedule_postseason",
        "v1/schedule/postseason",
        ("dates", "*", "games"),
        "Postseason games of a season.",
        ("gamePk",),
        "season",
        season="{season}",
    ),
    _ep(
        "schedule_postseason_series",
        "v1/schedule/postseason/series",
        ("series",),
        "Postseason series of a season.",
        ("series.id",),
        "season",
        season="{season}",
    ),
    _ep(
        "stats_leaders",
        "v1/stats/leaders",
        ("leagueLeaders", "*", "leaders"),
        "League leaders for every category of a season (ties repeat a rank, so the key is not unique).",
        ("leagueLeaders.leaderCategory", "leagueLeaders.statGroup", "rank"),
        "season",
        leaderCategories="{leader_categories}",
        season="{season}",
        sportId="{sport_id}",
        limit=100,
    ),
    _ep(
        "schedule_hydrated",
        "v1/schedule",
        ("dates", "*", "games"),
        "Season schedule with team, linescore, decisions, probable pitchers, officials, weather, venue, broadcasts, series and flags hydrated.",
        ("gamePk", "dates.date"),
        "season",
        sportId="{sport_id}",
        season="{season}",
        hydrate="team,linescore,decisions,probablePitcher,officials,weather,venue,broadcasts,series,flags",
    ),
    *_STANDINGS,
    _ep(
        "game_feed_plays",
        "v1.1/game/{game_pk}/feed/live",
        ("liveData", "plays", "allPlays"),
        "Every plate appearance of a final game from the live feed (result, about, count, matchup).",
        ("game_pk", "about.atBatIndex"),
        "game",
    ),
    _ep(
        "game_feed_play_events",
        "v1.1/game/{game_pk}/feed/live",
        ("liveData", "plays", "allPlays", "*", "playEvents"),
        "Every pitch/action event of a final game (pitchData, hitData, details, count) with its plate appearance's context.",
        ("game_pk", "allPlays.about.atBatIndex", "index"),
        "game",
    ),
    _ep(
        "game_feed_linescore_innings",
        "v1.1/game/{game_pk}/feed/live",
        ("liveData", "linescore", "innings"),
        "Inning-by-inning linescore from the live feed.",
        ("game_pk", "num"),
        "game",
    ),
    _ep(
        "game_feed_officials",
        "v1.1/game/{game_pk}/feed/live",
        ("liveData", "boxscore", "officials"),
        "Umpires of a final game from the live feed.",
        ("game_pk", "officialType"),
        "game",
    ),
    _ep(
        "game_boxscore_players",
        "v1/game/{game_pk}/boxscore",
        ("teams", "@", "players", "@"),
        "Every player line of a game boxscore (person, position, batting/pitching/fielding stats, season stats, game status) with its team context.",
        ("game_pk", "teams.key", "person.id"),
        "game",
    ),
    _ep(
        "game_boxscore_teams",
        "v1/game/{game_pk}/boxscore",
        ("teams", "@"),
        "Team totals of a game boxscore (team, teamStats, batters/pitchers/bench/bullpen id lists and info as JSON).",
        ("game_pk", "teams.key"),
        "game",
    ),
    _ep(
        "game_boxscore_officials",
        "v1/game/{game_pk}/boxscore",
        ("officials",),
        "Umpires of a game from the boxscore.",
        ("game_pk", "officialType"),
        "game",
    ),
    _ep(
        "game_boxscore_info",
        "v1/game/{game_pk}/boxscore",
        ("info",),
        "Game info label/value lines (weather, attendance, venue, first pitch, ...).",
        ("game_pk", "label"),
        "game",
    ),
    _ep(
        "game_boxscore_pitching_notes",
        "v1/game/{game_pk}/boxscore",
        ("pitchingNotes",),
        "Pitching notes of a game (one text line each).",
        ("game_pk", "value"),
        "game",
    ),
    _ep(
        "game_boxscore_top_performers",
        "v1/game/{game_pk}/boxscore",
        ("topPerformers",),
        "Top performers of a game from the boxscore.",
        ("game_pk", "type", "player.person.id"),
        "game",
    ),
    _ep(
        "game_linescore",
        "v1/game/{game_pk}/linescore",
        ("innings",),
        "Inning-by-inning linescore of a game.",
        ("game_pk", "num"),
        "game",
    ),
    _ep(
        "game_win_probability",
        "v1/game/{game_pk}/winProbability",
        (),
        "Win probability after every play.",
        ("game_pk", "atBatIndex"),
        "game",
    ),
    _ep(
        "game_play_by_play",
        "v1/game/{game_pk}/playByPlay",
        ("allPlays",),
        "Every play of a game (matchup, result, count, runners as JSON).",
        ("game_pk", "atBatIndex"),
        "game",
    ),
    MlbEndpoint(
        "attendance",
        "v1/attendance",
        ("records",),
        "Attendance by team-season.",
        ("team.id", "year"),
        "season",
        {"leagueId": "103,104", "season": "{season}"},
        "reference",
        unsupported="probe returned HTTP 400 with leagueId/season; see docs/mlb_probe.json",
        verified_on="2026-10-27",
        tried=("GET /v1/attendance?leagueId=103,104&season=2024 -> HTTP 400",),
    ),
    MlbEndpoint(
        "game_color",
        "v1/game/{game_pk}/feed/color",
        (),
        "Game color feed.",
        (),
        "game",
        unsupported="route answers 404 for a final game (probed 2026-10-27)",
        verified_on="2026-10-27",
        tried=("GET /v1/game/745000/feed/color -> HTTP 404",),
    ),
    MlbEndpoint(
        "home_run_derby",
        "v1/homeRunDerby/{game_pk}",
        (),
        "Home run derby bracket.",
        (),
        "game",
        unsupported="route answers 404 for the probed game (probed 2026-10-27)",
        verified_on="2026-10-27",
        tried=("GET /v1/homeRunDerby/511073 -> HTTP 404",),
    ),
    MlbEndpoint(
        "ref_sky_conditions",
        "v1/skyConditions",
        (),
        "Sky condition codes.",
        ("code",),
        unsupported="route answers 404 (probed 2026-10-27)",
        verified_on="2026-10-27",
        tried=("GET /v1/skyConditions -> HTTP 404",),
    ),
)

BY_NAME: dict[str, MlbEndpoint] = {e.name: e for e in ENDPOINTS}
SUPPORTED: tuple[MlbEndpoint, ...] = tuple(e for e in ENDPOINTS if e.unsupported is None)
