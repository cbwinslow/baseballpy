"""Baseball Savant leaderboard registry: one :class:`LeaderboardDef` per leaderboard *variant*.

Every variant becomes its own dataset (``statcast.leaderboard_<slug>``) with a strict schema
generated from the real headers (``lb_tables.py``, produced by ``scripts/gen_schemas.py savant``).
Routes that do not offer CSV (or answer 404) are kept with an explicit ``unsupported`` reason so the
coverage gap is documented rather than silently absent.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

SAVANT_BASE = "https://baseballsavant.mlb.com/leaderboard"


@dataclass(frozen=True)
class LeaderboardDef:
    """How to request one leaderboard variant and what one row means."""

    slug: str
    route: str
    description: str
    granularity: str
    keys: tuple[str, ...]
    params: Mapping[str, str | int] = field(default_factory=dict)
    #: how the season is sent: ``year`` (``year=``), ``year_span`` (``year=`` plus ``startYear``/
    #: ``endYear``), ``season_range`` (``seasonStart``/``seasonEnd``), ``season_snake`` (``season_start``/
    #: ``season_end``), ``season`` or ``none`` (route ignores the season: one flat snapshot)
    year_style: str = "year"
    #: minimum-qualifier request parameter (``None`` if the route has none)
    min_param: str | None = None
    #: ``csv`` = ``csv=true`` download, ``html_json`` = JSON array embedded in the HTML page
    fmt: str = "csv"
    #: name of the JS variable holding the rows when ``fmt == "html_json"``
    html_var: str = "data"
    unsupported: str | None = None
    #: when the ``unsupported`` verdict was last verified and what was tried
    verified_on: str | None = None
    tried: tuple[str, ...] = ()

    @property
    def dataset(self) -> str:
        """Registry dataset name."""
        return f"leaderboard_{self.slug}"


_PLAYER = ("player_id", "year")


#: variants whose season parameter is not plain ``year=`` (verified live: ``year=`` is ignored there)
_YEAR_STYLES = {
    "baserunning": "season_snake",
    "baserunning_run_value": "season_snake",
    "basestealing_run_value": "season_snake",
    "catcher_blocking": "season_snake",
    "bat_tracking": "season_range",
    "swing_path_attack_angle": "season_range",
    "catcher_framing": "season_range",
    "pitch_tempo": "season_snake",
    "pitch_clock": "season",
    "abs_challenges": "none",
    "fielding_run_value": "season_range",
    "rolling": "none",
}


def _lb(
    slug: str,
    route: str,
    description: str,
    granularity: str,
    keys: tuple[str, ...],
    *,
    min_param: str | None = None,
    **kwargs: object,
) -> LeaderboardDef:
    kwargs.setdefault("year_style", _YEAR_STYLES.get(slug, "year"))
    return LeaderboardDef(
        slug=slug,
        route=route,
        description=description,
        granularity=granularity,
        keys=keys,
        min_param=min_param,
        **kwargs,  # type: ignore[arg-type]
    )


LEADERBOARDS: tuple[LeaderboardDef, ...] = (
    _lb(
        "expected_statistics_batter",
        "expected_statistics",
        "Expected stats (xBA, xSLG, xwOBA) per batter-season.",
        "player-season",
        _PLAYER,
        params={"type": "batter"},
        min_param="min",
    ),
    _lb(
        "expected_statistics_pitcher",
        "expected_statistics",
        "Expected stats (xBA, xSLG, xwOBA, xERA) per pitcher-season.",
        "player-season",
        _PLAYER,
        params={"type": "pitcher"},
        min_param="min",
    ),
    _lb(
        "exit_velocity_batter",
        "statcast",
        "Exit velocity, launch angle and barrels per batter-season (batted-ball events).",
        "player-season",
        ("player_id",),
        params={"type": "batter"},
        min_param="min",
    ),
    _lb(
        "exit_velocity_pitcher",
        "statcast",
        "Exit velocity, launch angle and barrels allowed per pitcher-season.",
        "player-season",
        ("player_id",),
        params={"type": "pitcher"},
        min_param="min",
    ),
    _lb(
        "exit_velocity_batter_team",
        "statcast",
        "Exit velocity and barrels per batting team-season.",
        "team-season",
        ("team_id",),
        params={"type": "batter-team"},
        min_param="min",
    ),
    _lb(
        "exit_velocity_pitcher_team",
        "statcast",
        "Exit velocity and barrels allowed per pitching team-season.",
        "team-season",
        ("team_id",),
        params={"type": "pitcher-team"},
        min_param="min",
    ),
    _lb(
        "sprint_speed",
        "sprint_speed",
        "Sprint speed (ft/s on competitive runs) per player-season.",
        "player-season",
        ("player_id",),
        min_param="min",
    ),
    _lb(
        "running_splits",
        "running_splits",
        "90-foot running splits (time since contact at each 5-foot mark) per player-season.",
        "player-season-position",
        ("player_id", "team_id", "position_name", "bat_side"),
        min_param="min",
    ),
    _lb(
        "baserunning",
        "baserunning",
        "Extra-base-taken baserunning run value per runner-season.",
        "player-season",
        ("entity_id", "year"),
        params={"type": "Batter"},
        min_param="min",
    ),
    _lb(
        "baserunning_run_value",
        "baserunning-run-value",
        "Baserunning run value breakdown (extra bases, steal-of-base, swipe/snipe/freeze).",
        "player-span",
        ("player_id", "start_year", "end_year"),
        min_param="min",
    ),
    _lb(
        "basestealing_run_value",
        "basestealing-run-value",
        "Base-stealing run value and lead metrics by target base.",
        "player-span-base",
        ("player_id", "start_year", "end_year", "key_target_base"),
        min_param="min",
    ),
    _lb(
        "bat_tracking",
        "bat-tracking",
        "Bat speed, swing length, squared-up and blast rates per batter-season (2023+).",
        "player-season",
        ("id",),
        params={"type": "batter"},
        min_param="minSwings",
    ),
    _lb(
        "swing_path_attack_angle",
        "bat-tracking/swing-path-attack-angle",
        "Swing path: attack angle, attack direction and swing tilt per batter-season (2023+).",
        "player-season-side",
        ("id", "side"),
        params={"type": "batter"},
        min_param="minSwings",
    ),
    _lb(
        "outs_above_average",
        "outs_above_average",
        "Outs Above Average (OAA) and fielding runs prevented per fielder-position-season.",
        "player-position-season",
        ("player_id", "year", "primary_pos_formatted"),
        params={"type": "Fielder"},
        year_style="year_span",
        min_param="min",
    ),
    _lb(
        "outfield_jump",
        "outfield_jump",
        "Outfielder jump (reaction, burst and routing distance) per fielder-season.",
        "player-season",
        ("resp_fielder_id", "year"),
        min_param="min",
    ),
    _lb(
        "arm_strength",
        "arm-strength",
        "Fielder arm strength (max and per-base average) per player-season.",
        "player-season",
        ("player_id",),
        params={"type": "Fielder"},
        min_param="min",
    ),
    _lb(
        "poptime",
        "poptime",
        "Catcher pop time and arm strength on steal attempts per catcher-season.",
        "player-season",
        ("entity_id",),
        min_param="min",
    ),
    _lb(
        "catcher_framing",
        "catcher-framing",
        "Catcher framing runs by zone per catcher-season.",
        "player-season",
        ("id",),
        min_param="min",
    ),
    _lb(
        "catcher_blocking",
        "catcher-blocking",
        "Catcher blocking runs and blocks above average per catcher-span.",
        "player-span",
        ("player_id", "start_year"),
        min_param="min",
    ),
    _lb(
        "pitch_arsenals",
        "pitch-arsenals",
        "Average velocity per pitch type per pitcher-season (switch pitchers have one row per arm).",
        "player-season",
        ("pitcher",),
        params={"type": "avg_speed", "pitchType": ""},
        min_param="min",
    ),
    _lb(
        "pitch_arsenal_stats",
        "pitch-arsenal-stats",
        "Results (run value, BA, SLG, wOBA, whiff%) per pitcher and pitch type.",
        "player-season-pitch",
        ("player_id", "pitch_type"),
        params={"type": "pitcher", "pitchType": "", "team": ""},
        min_param="min",
    ),
    _lb(
        "pitch_movement",
        "pitch-movement",
        "Pitch movement (induced vertical and horizontal break) per pitcher and pitch type.",
        "player-season-pitch",
        ("pitcher_id", "pitch_type", "pitch_hand"),
        params={"pitch_type": "ALL", "hand": ""},
        min_param="min",
    ),
    _lb(
        "pitch_tempo",
        "pitch-tempo",
        "Time between pitches (median seconds by situation) per pitcher-season.",
        "player-season",
        ("entity_id",),
        min_param="min",
    ),
    _lb(
        "spin_direction_pitches",
        "spin-direction-pitches",
        "Measured vs inferred spin direction and active spin per pitcher and pitch type.",
        "player-season-pitch",
        ("player_id", "api_pitch_type"),
        min_param="min",
    ),
    _lb(
        "percentile_rankings_batter",
        "percentile-rankings",
        "Statcast percentile inputs per batter-season.",
        "player-season",
        _PLAYER,
        params={"type": "batter"},
    ),
    _lb(
        "percentile_rankings_pitcher",
        "percentile-rankings",
        "Statcast percentile inputs per pitcher-season.",
        "player-season",
        _PLAYER,
        params={"type": "pitcher"},
    ),
    _lb(
        "home_runs",
        "home-runs",
        "Home run tracking (no-doubters, expected home runs) per player-season.",
        "player-season-type",
        ("player_id", "year", "type"),
        params={"type": "batter"},
    ),
    _lb(
        "batted_ball",
        "batted-ball",
        "Batted-ball profile (pull/straight/oppo, ground/line/fly rates) per batter-season.",
        "player-season",
        ("id", "year"),
        params={"type": "batter"},
        min_param="min",
    ),
    _lb(
        "swing_take",
        "swing-take",
        "Swing/take run value by zone region per batter-season.",
        "player-season",
        ("player_id", "year"),
        min_param="min",
    ),
    _lb(
        "abs_challenges",
        "abs-challenges",
        "Automated ball-strike challenge system results per player (2025+; empty before).",
        "player-season-level",
        ("entity_name", "team_abbr", "year", "level"),
        params={"type": "batter"},
        min_param="min",
    ),
    _lb(
        "pitch_clock",
        "pitch-timer-infractions",
        "Pitch-timer violations by kind per player-season (2023+).",
        "player-season",
        ("entity_id", "year"),
    ),
    _lb(
        "fielding_run_value",
        "fielding-run-value",
        "Fielding run value by fielder (embedded JSON rows of the page, no qualifier).",
        "player-season",
        ("id", "team_id"),
        params={"gameType": "Regular", "type": "fielder"},
        fmt="html_json",
    ),
    _lb(
        "rolling",
        "rolling",
        "Rolling last-N-batted-ball xwOBA windows (50/100/250) per batter and pitcher: a snapshot of the current season (the page ignores the season parameter).",
        "player-window",
        ("player_id", "cat", "cat_bin"),
        html_var="rolling",
        fmt="html_json",
    ),
    _lb(
        "active_spin",
        "active-spin",
        "Active spin (measured vs inferred) per pitcher and pitch type; the `min` qualifier breaks this route, so it is not sent.",
        "player-season",
        ("entity_id", "pitch_hand"),
    ),
    _lb(
        "catch_probability",
        "catch_probability",
        "Fielder catch probability by star bucket (2016 onwards). The `type` parameter empties this route (and produced anonymous rows in an earlier probe), so it is not sent.",
        "player-season",
        ("player_id",),
        min_param="min",
    ),
    _lb(
        "park_factors",
        "statcast-park-factors",
        "Statcast park factor indices per venue and 3-year span (embedded JSON on the page).",
        "venue-season",
        ("venue_id", "key_year"),
        params={
            "type": "year",
            "batSide": "",
            "stat": "index_wOBA",
            "condition": "All",
            "rolling": 3,
            "parks": "mlb",
        },
        fmt="html_json",
    ),
    LeaderboardDef(
        "directional_outs_above_average",
        "directional_outs_above_average",
        "Directional OAA.",
        "player-season",
        (),
        unsupported="route answers 404 (probed 2026-10-27); directions are columns of outs_above_average",
        verified_on="2026-10-27",
        tried=("GET /leaderboard/directional_outs_above_average?year=2024&csv=true -> HTTP 404",),
    ),
    LeaderboardDef(
        "catcher_throwing",
        "catcher_throwing",
        "Catcher throwing.",
        "player-season",
        (),
        unsupported="route answers 404; pop time/arm strength are in `poptime`",
        verified_on="2026-10-27",
        tried=("GET /leaderboard/catcher_throwing?year=2024&min=q&csv=true -> HTTP 404",),
    ),
    LeaderboardDef(
        "year_to_year",
        "year-to-year",
        "Year-to-year comparison.",
        "player-season",
        (),
        unsupported="route answers 404 (comparison tool, derivable from other leaderboards)",
        verified_on="2026-10-27",
        tried=("GET /leaderboard/year-to-year?year=2024&csv=true -> HTTP 404",),
    ),
    LeaderboardDef(
        "bat_speed",
        "bat-speed",
        "Bat speed.",
        "player-season",
        (),
        unsupported="route answers 404; bat speed is a column of bat_tracking",
        verified_on="2026-10-27",
        tried=("GET /leaderboard/bat-speed?year=2024&csv=true -> HTTP 404",),
    ),
)

BY_SLUG: dict[str, LeaderboardDef] = {d.slug: d for d in LEADERBOARDS}
SUPPORTED: tuple[LeaderboardDef, ...] = tuple(d for d in LEADERBOARDS if d.unsupported is None)

#: legacy ``get_leaderboard(name, type=...)`` names -> slug (so existing callers keep working)
LEGACY_NAMES: dict[str, str] = {
    "expected_statistics": "expected_statistics_batter",
    "exit_velocity": "exit_velocity_batter",
    "bat_tracking": "bat_tracking",
    "sprint_speed": "sprint_speed",
    "running_splits": "running_splits",
    "outs_above_average": "outs_above_average",
    "arm_strength": "arm_strength",
    "poptime": "poptime",
    "catcher_framing": "catcher_framing",
    "pitch_arsenals": "pitch_arsenals",
    "pitch_movement": "pitch_movement",
    "abs_challenges": "abs_challenges",
}


def resolve(name: str, player_type: str | None = None) -> LeaderboardDef:
    """Look up a variant by slug or legacy name (``player_type`` picks batter/pitcher variants)."""
    key = name.lower().replace("-", "_")
    if key in BY_SLUG:
        return BY_SLUG[key]
    if player_type is not None and f"{key}_{player_type}" in BY_SLUG:
        return BY_SLUG[f"{key}_{player_type}"]
    if key in LEGACY_NAMES:
        return BY_SLUG[LEGACY_NAMES[key]]
    raise KeyError(f"unknown Savant leaderboard {name!r}; known: {sorted(BY_SLUG)}")


def request_params(
    defn: LeaderboardDef, year: int, min_value: str | None = None
) -> dict[str, str | int]:
    """Query parameters for one season of a variant (``min_value`` overrides the default)."""
    params: dict[str, str | int] = dict(defn.params)
    if defn.fmt == "csv":
        params["csv"] = "true"
    style = defn.year_style
    if style in ("year", "year_span"):
        params["year"] = year
    if style == "year_span":
        params["startYear"] = year
        params["endYear"] = year
    if style == "season_range":
        params["seasonStart"] = year
        params["seasonEnd"] = year
    if style == "season":
        params["season"] = year
    if style == "season_snake":
        params["season_start"] = year
        params["season_end"] = year
    if defn.min_param is not None and min_value is not None:
        params[defn.min_param] = min_value
    return params
