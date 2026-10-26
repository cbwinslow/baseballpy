"""Canonical PyArrow schema for Chadwick Bureau Player Register."""

import pyarrow as pa

CHADWICK_PEOPLE_SCHEMA = pa.schema(
    [
        ("key_person", pa.string()),
        ("key_uuid", pa.string()),
        ("key_mlbam", pa.int32()),
        ("key_retro", pa.string()),
        ("key_bbref", pa.string()),
        ("key_fangraphs", pa.int32()),
        ("name_last", pa.string()),
        ("name_first", pa.string()),
        ("name_given", pa.string()),
        ("birth_year", pa.int16()),
        ("birth_month", pa.int8()),
        ("birth_day", pa.int8()),
        ("mlb_played_first", pa.int16()),
        ("mlb_played_last", pa.int16()),
    ]
)
