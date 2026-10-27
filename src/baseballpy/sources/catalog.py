"""Registers every dataset the sources currently produce in the shared dataset registry.

``complete-source-coverage`` extends this module as endpoints are added; nothing outside the
registry should hardcode a dataset name.
"""

from typing import Literal

import pyarrow as pa

from baseballpy.core.datasets import DATASETS, DatasetSpec, register
from baseballpy.sources.chadwick.schema import (
    CHADWICK_LINKS_SCHEMA,
    CHADWICK_NAMES_SCHEMA,
    CHADWICK_PEOPLE_SCHEMA,
)
from baseballpy.sources.lahman.schema import LAHMAN_PRIMARY_KEYS, LAHMAN_SCHEMAS
from baseballpy.sources.mlb_api import schemas as mlb
from baseballpy.sources.retrosheet import schema as retro
from baseballpy.sources.statcast.schema import STATCAST_SCHEMA

Partition = Literal["season", "none"]


def _add(
    source: str,
    name: str,
    view: str,
    schema: pa.Schema,
    keys: tuple[str, ...],
    description: str,
    endpoint_doc: str,
    partition: str = "none",
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
        )
    )


def register_all() -> dict[str, DatasetSpec]:
    """Idempotently register every known dataset and return the registry."""
    _add(
        "statcast",
        "pitches",
        "statcast_pitches",
        STATCAST_SCHEMA,
        ("game_pk", "at_bat_number", "pitch_number"),
        "Pitch-level Statcast search results.",
        "sources/statcast.md#1-granular-pitch-level-search-endpoint-statcast_searchcsv",
        "season",
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
    _add(
        "chadwick",
        "register",
        "chadwick_register",
        CHADWICK_PEOPLE_SCHEMA,
        ("key_person",),
        "Master player-ID crosswalk (people-*.csv shards).",
        chadwick_doc,
    )
    _add(
        "chadwick",
        "names",
        "chadwick_names",
        CHADWICK_NAMES_SCHEMA,
        ("key_person", "name_type", "name_last", "name_first"),
        "Alternate names and nicknames.",
        chadwick_doc,
    )
    _add(
        "chadwick",
        "links",
        "chadwick_links",
        CHADWICK_LINKS_SCHEMA,
        ("key_person", "link_type", "link_url"),
        "External player links.",
        chadwick_doc,
    )

    retro_doc = "sources/retrosheet.md"
    for r_name, r_schema, r_keys, r_part, r_anchor, r_desc in (
        (
            "events",
            retro.RETROSHEET_EVENT_SCHEMA,
            ("GAME_ID",),
            "season",
            "1-play-by-play-event-data-eva-evn-eve-eb",
            "Regular-season play-by-play events.",
        ),
        (
            "events_postseason",
            retro.RETROSHEET_EVENT_SCHEMA,
            ("GAME_ID",),
            "season",
            "1-play-by-play-event-data-eva-evn-eve-eb",
            "Postseason and all-star play-by-play events.",
        ),
        (
            "boxscores_batting",
            retro.RETROSHEET_BOX_BATTING_SCHEMA,
            ("game_id", "team_id", "player_id", "slot"),
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
            ("GAME_ID", "TEAM_ID", "PLAYER_ID"),
            "season",
            "4-daily-player-splits-daily",
            "Daily player appearance lines.",
        ),
        (
            "substitutions",
            retro.RETROSHEET_SUBSTITUTIONS_SCHEMA,
            ("GAME_ID", "EVENT_ID"),
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
            ("year", "team", "player_id"),
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
        )

    for ref_name, ref_schema, ref_keys, ref_anchor in (
        (
            "ballparks",
            retro.RETROSHEET_BALLPARKS_SCHEMA,
            ("park_id",),
            "a-ballparks-referenceballparkscsv",
        ),
        (
            "teams",
            retro.RETROSHEET_TEAMS_SCHEMA,
            ("team_id", "first_year"),
            "b-teams-referenceteamscsv",
        ),
        (
            "ejections",
            retro.RETROSHEET_EJECTIONS_SCHEMA,
            ("game_id", "ejectee_id"),
            "c-ejections-referenceejectionscsv",
        ),
        (
            "coaches",
            retro.RETROSHEET_COACHES_SCHEMA,
            ("coach_id", "year", "team_id", "role"),
            "d-coaching-staffs-referencecoachescsv",
        ),
        (
            "relatives",
            retro.RETROSHEET_RELATIVES_SCHEMA,
            ("id1", "relation", "id2"),
            "e-relatives-referencerelativescsv",
        ),
        (
            "biofile",
            retro.RETROSHEET_BIOFILE_SCHEMA,
            ("player_id",),
            "f-biographical-file-referencebiofilecsv",
        ),
    ):
        _add(
            "retrosheet",
            f"reference_{ref_name}",
            f"retrosheet_reference_{ref_name}",
            ref_schema,
            ref_keys,
            f"Retrosheet reference table: {ref_name}.",
            f"{retro_doc}#{ref_anchor}",
        )

    return DATASETS


register_all()
