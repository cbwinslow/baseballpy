"""Registers every dataset the sources currently produce in the shared dataset registry.

``complete-source-coverage`` extends this module as endpoints are added; nothing outside the
registry should hardcode a dataset name.
"""

from typing import Literal

import pyarrow as pa

from baseballpy.core import datasets as _datasets_module
from baseballpy.core.datasets import DatasetSpec, IngestMode, register
from baseballpy.core.schema_tools import snake
from baseballpy.sources.chadwick.schema import CHADWICK_PRIMARY_KEYS, CHADWICK_SCHEMAS
from baseballpy.sources.lahman.schema import LAHMAN_PRIMARY_KEYS, LAHMAN_SCHEMAS
from baseballpy.sources.mlb_api import schemas as mlb
from baseballpy.sources.mlb_api.endpoints import SUPPORTED as MLB_ENDPOINTS
from baseballpy.sources.mlb_api.mlb_schema import MLB_SCHEMAS
from baseballpy.sources.retrosheet import schema as retro
from baseballpy.sources.retrosheet.box_parser import SCHEMAS as BOX_SCHEMAS
from baseballpy.sources.retrosheet.schema import RETROSHEET_FLAT_KEYS, RETROSHEET_FLAT_SCHEMAS
from baseballpy.sources.statcast.lb_catalog import SUPPORTED as SAVANT_LEADERBOARDS
from baseballpy.sources.statcast.lb_schema import LEADERBOARD_SCHEMAS
from baseballpy.sources.statcast.schema import STATCAST_SCHEMA

Partition = Literal["season", "none"]

#: default-ingested Retrosheet datasets that upstream publishes for some seasons only (checked
#: against the pinned ``chadwickbureau/retrosheet`` tree, 2026-10-28); an empty season is not a gap
RETROSHEET_COVERAGE_NOTES = {
    "events_deduced": "upstream has .ED* files for 1968 and earlier only",
    "discrepancies": "upstream has *discs.csv files for 1988 and earlier only",
    "schedule_original": "upstream has the original schedule for 2020 only",
}


def _add(
    source: str,
    name: str,
    view: str,
    schema: pa.Schema,
    keys: tuple[str, ...],
    description: str,
    endpoint_doc: str,
    partition: str = "none",
    ingest: IngestMode = "default",
    ingest_note: str = "",
) -> None:
    part: Partition = "season" if partition == "season" else "none"
    register(
        DatasetSpec(
            source=source,
            name=name,
            view=view,
            schema=schema,
            partition=part,
            keys=keys,
            description=description,
            endpoint_doc=endpoint_doc,
            ingest=ingest,
            ingest_note=ingest_note,
        )
    )


#: dataset keys registered by the last full pass (empty before the first one)
_REGISTERED_KEYS: frozenset[str] = frozenset()


def register_all() -> dict[str, DatasetSpec]:
    """Idempotently register every known dataset and return the registry.

    The full pass derives hundreds of definitions (about 5 ms), and callers invoke this on every
    load, so once a pass has completed it returns at once while the registry still holds all of its
    datasets; it runs again if the registry was replaced or cleared.
    """
    global _REGISTERED_KEYS
    if _REGISTERED_KEYS and _datasets_module.DATASETS.keys() >= _REGISTERED_KEYS:
        return _datasets_module.DATASETS
    _add(
        "statcast",
        "pitches",
        "statcast_pitches",
        STATCAST_SCHEMA,
        ("game_pk", "at_bat_number", "pitch_number"),
        "Pitch-level Statcast search results.",
        "sources/statcast.md#1-pitch-level-search-statcast_searchcsv---dataset-pitches",
        "season",
    )

    _add(
        "statcast",
        "pitches_minors",
        "statcast_pitches_minors",
        STATCAST_SCHEMA,
        ("game_pk", "at_bat_number", "pitch_number"),
        "Minor-league pitch-level Statcast search results (minors=true, 2021 onwards).",
        "sources/statcast.md#1-pitch-level-search-statcast_searchcsv---dataset-pitches",
        "season",
    )

    for board in SAVANT_LEADERBOARDS:
        if board.slug not in LEADERBOARD_SCHEMAS:
            continue  # variant added but its schema not generated yet (a test catches this)
        _add(
            "statcast",
            board.dataset,
            f"statcast_{board.dataset}",
            LEADERBOARD_SCHEMAS[board.slug],
            board.keys,
            board.description,
            "sources/statcast.md#2-leaderboards-leaderboardroute",
            "none" if board.year_style == "none" else "season",
        )

    mlb_doc = "sources/mlb_api.md"
    for name, schema, keys, partition, anchor, desc in (
        (
            "schedule",
            mlb.MLB_SCHEDULE_SCHEMA,
            ("game_pk",),
            "season",
            "1-schedule--calendar-endpoint-v1schedule",
            "Game schedule.",
        ),
        (
            "box_batting",
            mlb.MLB_BOX_BATTING_SCHEMA,
            ("game_pk", "team_id", "player_id"),
            "season",
            "a-batting-boxscore-mlb_box_batting",
            "Official batting boxscore lines.",
        ),
        (
            "box_pitching",
            mlb.MLB_BOX_PITCHING_SCHEMA,
            ("game_pk", "team_id", "player_id"),
            "season",
            "b-pitching-boxscore-mlb_box_pitching",
            "Official pitching boxscore lines.",
        ),
        (
            "standings",
            mlb.MLB_STANDINGS_SCHEMA,
            ("season", "team_id"),
            "season",
            "4-standings--rankings-v1standings",
            "League and division standings.",
        ),
        (
            "teams",
            mlb.MLB_TEAMS_SCHEMA,
            ("team_id",),
            "none",
            "5-teams--active-rosters-v1teams-v1teamsteam_idroster",
            "MLB franchises.",
        ),
        (
            "rosters",
            mlb.MLB_ROSTERS_SCHEMA,
            ("team_id", "player_id"),
            "none",
            "5-teams--active-rosters-v1teams-v1teamsteam_idroster",
            "Active team rosters.",
        ),
        (
            "transactions",
            mlb.MLB_TRANSACTIONS_SCHEMA,
            ("transaction_id",),
            "season",
            "6-transactions-v1transactions",
            "Roster transactions.",
        ),
        (
            "draft",
            mlb.MLB_DRAFT_SCHEMA,
            ("year", "pick_overall"),
            "season",
            "7-draft-v1draftyear",
            "First-year player draft picks.",
        ),
        (
            "venues",
            mlb.MLB_VENUES_SCHEMA,
            ("venue_id",),
            "none",
            "8-venues--ballparks-v1venues",
            "Official ballparks.",
        ),
    ):
        _add(
            "mlb_api",
            name,
            f"mlb_{name}",
            schema,
            keys,
            desc,
            f"{mlb_doc}#{anchor}",
            partition,
            "api_only",
            "hand-written; filled by MlbApiSource methods, its declarative twin is ingested",
        )

    for endpoint in MLB_ENDPOINTS:
        if endpoint.name not in MLB_SCHEMAS:
            continue  # no live data when the schemas were generated (see docs/mlb_probe.json)
        mode, note = endpoint.ingest_mode
        _add(
            "mlb_api",
            endpoint.name,
            f"mlb_{endpoint.name}",
            MLB_SCHEMAS[endpoint.name],
            tuple(snake(k) for k in endpoint.keys),
            endpoint.description,
            "sources/mlb_api.md#declarative-endpoints",
            "season" if endpoint.partitioned else "none",
            mode,
            note,
        )

    for table, schema in LAHMAN_SCHEMAS.items():
        table_name = str(table)
        _add(
            "lahman",
            table_name,
            f"lahman_{table_name.lower()}",
            schema,
            LAHMAN_PRIMARY_KEYS[table_name],
            f"Lahman {table_name} table.",
            "sources/lahman.md#all-27-supported-tables",
        )

    chadwick_doc = (
        "sources/chadwick.md#exhaustive-master-register-schema-dictionary-chadwick_people_schema"
    )
    for name, desc in (
        ("register", "Master player-ID crosswalk (data/people-*.csv shards)."),
        ("register_names", "Alternate names, spellings and nicknames (data/names.csv)."),
        ("register_links", "External player identifiers by source (data/links.csv)."),
        ("register_countries", "ISO / IOC / FIFA country codes (data/countries.csv)."),
    ):
        _add(
            "chadwick",
            name,
            f"chadwick_{name}",
            CHADWICK_SCHEMAS[name],
            CHADWICK_PRIMARY_KEYS[name],
            desc,
            chadwick_doc,
        )

    retro_doc = "sources/retrosheet.md"
    for r_name, r_schema, r_keys, r_part, r_anchor, r_desc in (
        (
            "events",
            retro.RETROSHEET_EVENT_SCHEMA,
            ("GAME_ID", "EVENT_ID"),
            "season",
            "1-play-by-play-event-data-eva-evn-eve-eb",
            "Regular-season play-by-play events.",
        ),
        (
            "events_postseason",
            retro.RETROSHEET_EVENT_SCHEMA,
            ("GAME_ID", "EVENT_ID"),
            "season",
            "1-play-by-play-event-data-eva-evn-eve-eb",
            "Postseason and all-star play-by-play events.",
        ),
        (
            "events_deduced",
            retro.RETROSHEET_EVENT_SCHEMA,
            ("GAME_ID", "EVENT_ID"),
            "season",
            "1-play-by-play-event-data-eva-evn-eve-eb",
            "Play-by-play events deduced from box scores (.ED* files).",
        ),
        (
            "boxscores_batting",
            retro.RETROSHEET_BOX_BATTING_SCHEMA,
            ("game_id", "team_id", "slot", "seq"),
            "season",
            "a-batting-box-score-table-retrosheet_box_batting",
            "Batting box score lines.",
        ),
        (
            "boxscores_pitching",
            retro.RETROSHEET_BOX_PITCHING_SCHEMA,
            ("game_id", "team_id", "pitcher_id", "seq"),
            "season",
            "b-pitching-box-score-table-retrosheet_box_pitching",
            "Pitching box score lines.",
        ),
        (
            "daily_splits",
            retro.RETROSHEET_DAILY_SPLITS_SCHEMA,
            ("GAME_ID", "TEAM_ID", "PLAYER_ID", "SLOT_CT", "SEQ_CT"),
            "season",
            "4-daily-player-splits-daily",
            "Daily player appearance lines.",
        ),
        (
            "substitutions",
            retro.RETROSHEET_SUBSTITUTIONS_SCHEMA,
            ("GAME_ID", "EVENT_ID", "SUB_ID"),
            "season",
            "5-substitutions-sub",
            "In-game substitutions.",
        ),
        (
            "gamelogs",
            retro.RETROSHEET_GAMELOG_SCHEMA,
            ("date", "game_num", "home_team"),
            "season",
            "2-historical-game-logs-1871present",
            "Regular-season game logs.",
        ),
        (
            "gamelogs_postseason",
            retro.RETROSHEET_GAMELOG_SCHEMA,
            ("date", "game_num", "home_team"),
            "none",
            "2-historical-game-logs-1871present",
            "Postseason and all-star game logs.",
        ),
        (
            "rosters",
            retro.RETROSHEET_ROSTER_SCHEMA,
            ("year", "roster", "player_id"),
            "season",
            "1-play-by-play-event-data-eva-evn-eve-eb",
            "Team rosters per season.",
        ),
    ):
        _add(
            "retrosheet",
            r_name,
            f"retrosheet_{r_name}",
            r_schema,
            r_keys,
            r_desc,
            f"{retro_doc}#{r_anchor}",
            r_part,
            ingest_note=RETROSHEET_COVERAGE_NOTES.get(r_name, ""),
        )

    flat_descriptions = {
        "reference_ballparks": "Ballparks (reference/ballparks.csv).",
        "reference_teams": "Franchise/team codes (reference/teams.csv).",
        "reference_ejections": "Ejections (reference/ejections.csv).",
        "reference_coaches": "Coaching staffs (reference/coaches.csv).",
        "reference_relatives": "Relatives among players/managers (reference/relatives.csv).",
        "reference_biofile": "Biographical file (reference/biofile.csv).",
        "reference_biofile0": "Biographical file, ISO-date edition (reference/biofile0.csv).",
        "schedule": "Season schedules (seasons/<year>/<year>schedule.csv).",
        "schedule_original": "Original pre-disruption schedules (seasons/<year>/<year>sched-orig.csv).",
        "umpires": "Umpires working each season (seasons/<year>/UMPIRES<year>.txt).",
        "discrepancies": "Known data discrepancies (seasons/<year>/*discs.csv).",
    }
    seasonal = {"schedule", "schedule_original", "umpires", "discrepancies"}
    for flat_name, flat_schema in RETROSHEET_FLAT_SCHEMAS.items():
        _add(
            "retrosheet",
            flat_name,
            f"retrosheet_{flat_name}",
            flat_schema,
            RETROSHEET_FLAT_KEYS[flat_name],
            flat_descriptions[flat_name],
            f"{retro_doc}#dataset-{flat_name}",
            "season" if flat_name in seasonal else "none",
            ingest_note=RETROSHEET_COVERAGE_NOTES.get(flat_name, ""),
        )

    box_doc = f"{retro_doc}#3b-box-score-game-accounts-eba-ebn-ebe-ebr-ebf"
    for box_name, box_keys, box_desc in (
        ("box_games", ("game_id",), "Games of the box-score accounts (id, version, info lines)."),
        (
            "box_starters",
            ("game_id", "player_id", "side"),
            "Starting lineups of the box-score accounts (start lines).",
        ),
        (
            "box_batting_lines",
            ("game_id", "player_id", "side", "seq"),
            "Batting and base-running lines of the box-score accounts (stat,bline).",
        ),
        (
            "box_records",
            ("game_id", "line_no"),
            "Every other box-account record (pinch hitters/runners, fielding, pitching, team totals, "
            "line scores, events, comments, unknown kinds) as parsed fields plus the raw line.",
        ),
    ):
        _add(
            "retrosheet",
            box_name,
            f"retrosheet_{box_name}",
            BOX_SCHEMAS[box_name],
            box_keys,
            box_desc,
            box_doc,
            "season",
        )

    _REGISTERED_KEYS = frozenset(_datasets_module.DATASETS)
    return _datasets_module.DATASETS


register_all()
