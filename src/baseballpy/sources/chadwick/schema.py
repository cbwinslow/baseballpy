"""Canonical PyArrow schemas and Enums for Chadwick Bureau Player Register."""

from enum import StrEnum

import pyarrow as pa


class PlayerIdType(StrEnum):
    """Supported player identifier systems in the Chadwick Register."""

    PERSON = "key_person"
    UUID = "key_uuid"
    MLBAM = "key_mlbam"
    RETRO = "key_retro"
    BBREF = "key_bbref"
    BBREF_MINORS = "key_bbref_minors"
    FANGRAPHS = "key_fangraphs"
    NPB = "key_npb"
    WIKIDATA = "key_wikidata"


CHADWICK_PEOPLE_SCHEMA = pa.schema(
    [
        ("key_person", pa.string()),
        ("key_uuid", pa.string()),
        ("key_mlbam", pa.int32()),
        ("key_retro", pa.string()),
        ("key_bbref", pa.string()),
        ("key_bbref_minors", pa.string()),
        ("key_fangraphs", pa.int32()),
        ("key_npb", pa.string()),
        ("key_sr_nfl", pa.string()),
        ("key_sr_nba", pa.string()),
        ("key_sr_nhl", pa.string()),
        ("key_wikidata", pa.string()),
        ("name_last", pa.string()),
        ("name_first", pa.string()),
        ("name_given", pa.string()),
        ("name_suffix", pa.string()),
        ("name_matrilineal", pa.string()),
        ("name_nick", pa.string()),
        ("birth_year", pa.int16()),
        ("birth_month", pa.int8()),
        ("birth_day", pa.int8()),
        ("death_year", pa.int16()),
        ("death_month", pa.int8()),
        ("death_day", pa.int8()),
        ("pro_played_first", pa.int16()),
        ("pro_played_last", pa.int16()),
        ("mlb_played_first", pa.int16()),
        ("mlb_played_last", pa.int16()),
        ("col_played_first", pa.int16()),
        ("col_played_last", pa.int16()),
    ]
)

CHADWICK_NAMES_SCHEMA = pa.schema(
    [
        ("key_person", pa.string()),
        ("name_last", pa.string()),
        ("name_first", pa.string()),
        ("name_given", pa.string()),
        ("name_suffix", pa.string()),
        ("name_matrilineal", pa.string()),
        ("name_nick", pa.string()),
        ("name_type", pa.string()),
    ]
)

CHADWICK_LINKS_SCHEMA = pa.schema(
    [
        ("key_person", pa.string()),
        ("link_type", pa.string()),
        ("link_url", pa.string()),
    ]
)
