"""Strict PyArrow schemas (generated from the real headers) and Enums for the Chadwick Register."""

from enum import StrEnum

import pyarrow as pa

from baseballpy.core.schema_tools import schema_from_columns
from baseballpy.sources.chadwick.tables import CHADWICK_COLUMNS, CHADWICK_KEYS


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


#: Strict schema per dataset (typed columns + trailing ``_extras`` JSON string).
CHADWICK_SCHEMAS: dict[str, pa.Schema] = {
    dataset: schema_from_columns(columns) for dataset, columns in CHADWICK_COLUMNS.items()
}
#: Documented key per dataset (uniqueness verified on the full register).
CHADWICK_PRIMARY_KEYS = CHADWICK_KEYS

CHADWICK_PEOPLE_SCHEMA = CHADWICK_SCHEMAS["register"]
CHADWICK_NAMES_SCHEMA = CHADWICK_SCHEMAS["register_names"]
CHADWICK_LINKS_SCHEMA = CHADWICK_SCHEMAS["register_links"]
CHADWICK_COUNTRIES_SCHEMA = CHADWICK_SCHEMAS["register_countries"]
