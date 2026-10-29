"""Chadwick Bureau Player Register: the typed table with lazy id indexes, crosswalk and name search."""

import logging
import time
from dataclasses import dataclass, fields
from typing import Any

import narwhals as nw
import polars as pl
import pyarrow as pa
import pyarrow.compute as pc

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.similarity import top_matches
from baseballpy.core.stores import ProcessedStore
from baseballpy.sources import catalog
from baseballpy.sources.chadwick.extractor import ChadwickExtractor
from baseballpy.sources.chadwick.ingest import ingest
from baseballpy.sources.chadwick.schema import PlayerIdType
from baseballpy.sources.chadwick.search import learn_nicknames

logger = logging.getLogger(__name__)

#: ``PlayerIdType.value`` is the register column and the ``PlayerRecord`` field; these sets say how
#: an id of that type is compared (integers are coerced, some text ids ignore case).
_INT_IDS = frozenset({PlayerIdType.MLBAM, PlayerIdType.FANGRAPHS, PlayerIdType.NPB})
_CASEFOLDED_IDS = frozenset(
    {
        PlayerIdType.PERSON,
        PlayerIdType.UUID,
        PlayerIdType.RETRO,
        PlayerIdType.BBREF,
        PlayerIdType.BBREF_MINORS,
    }
)
_ID_TYPES = {id_type.value: id_type for id_type in PlayerIdType}

_REQUIRED = frozenset({"key_person", "key_uuid"})

#: registers kept for the process: ``(lake home, register manifest stamp) -> (loaded at, register)``
_LOADED: dict[tuple[str, int], tuple[float, "ChadwickRegister"]] = {}


def _lake_stamp(config: LakeConfig) -> int:
    """Changes whenever the processed register is rewritten (0 when it does not exist yet)."""
    try:
        return (config.processed_dir("chadwick", "register") / "manifest.json").stat().st_mtime_ns
    except OSError:
        return 0


#: how many matches a fuzzy search returns
FUZZY_LIMIT = 10


def _id_type(value: PlayerIdType | str) -> PlayerIdType:
    """The ``PlayerIdType`` for an enum member, ``"key_mlbam"`` or ``"mlbam"``."""
    text = str(value).lower()
    for candidate in (text, f"key_{text}"):
        if candidate in _ID_TYPES:
            return _ID_TYPES[candidate]
    raise ValueError(f"unknown player id type {value!r}; known: {sorted(_ID_TYPES)}")


def _normalise_id(id_type: PlayerIdType, value: Any) -> Any:
    """The form in which ``value`` is stored in and looked up from the index of ``id_type``.

    ``None`` means the value cannot be an id of that type (empty, or not a number for an integer id).
    """
    if value is None or value == "":
        return None
    if id_type in _INT_IDS:
        try:
            return int(value)
        except (ValueError, TypeError):
            try:
                return int(float(value))
            except (ValueError, TypeError):
                return None
    text = str(value).strip()
    return text.lower() if id_type in _CASEFOLDED_IDS else text


@dataclass(frozen=True, slots=True)
class PlayerRecord:
    """Strongly-typed player identifier crosswalk record."""

    key_person: str
    key_uuid: str
    key_mlbam: int | None = None
    key_retro: str | None = None
    key_bbref: str | None = None
    key_bbref_minors: str | None = None
    key_fangraphs: int | None = None
    key_npb: int | None = None
    key_sr_nfl: str | None = None
    key_sr_nba: str | None = None
    key_sr_nhl: str | None = None
    key_wikidata: str | None = None
    name_last: str | None = None
    name_first: str | None = None
    name_given: str | None = None
    name_suffix: str | None = None
    name_matrilineal: str | None = None
    name_nick: str | None = None
    birth_year: int | None = None
    birth_month: int | None = None
    birth_day: int | None = None
    death_year: int | None = None
    death_month: int | None = None
    death_day: int | None = None
    pro_played_first: int | None = None
    pro_played_last: int | None = None
    mlb_played_first: int | None = None
    mlb_played_last: int | None = None
    col_played_first: int | None = None
    col_played_last: int | None = None
    pro_managed_first: int | None = None
    pro_managed_last: int | None = None
    mlb_managed_first: int | None = None
    mlb_managed_last: int | None = None
    col_managed_first: int | None = None
    col_managed_last: int | None = None
    pro_umpired_first: int | None = None
    pro_umpired_last: int | None = None
    mlb_umpired_first: int | None = None
    mlb_umpired_last: int | None = None

    @property
    def full_name(self) -> str:
        """Formatted full player name."""
        first = self.name_first or ""
        last = self.name_last or ""
        return f"{first} {last}".strip()

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PlayerRecord":
        """Build a record from one register row (columns the register lacks become ``None``)."""
        rest = {f.name: row.get(f.name) for f in fields(cls) if f.name not in _REQUIRED}
        return cls(key_person=row["key_person"], key_uuid=row["key_uuid"], **rest)


class ChadwickRegister:
    """The player register with id crosswalk and name search.

    Nothing is indexed up front: each id index is built the first time that id type is used (from
    the non-null values only, with Arrow), and names are searched with vectorised string
    operations. Constructing a register is free.
    """

    def __init__(
        self,
        table: pa.Table,
        names_table: pa.Table | None = None,
        links_table: pa.Table | None = None,
        countries_table: pa.Table | None = None,
    ) -> None:
        self._table = table
        self._names_table = names_table
        self._links_table = links_table
        self._countries_table = countries_table
        self._polars: pl.DataFrame | None = None
        self._id_index: dict[PlayerIdType, dict[Any, int]] = {}
        self._lower_names: pl.Series | None = None
        self._nicknames: dict[str, tuple[str, ...]] | None = None
        self._aliases: dict[str, list[int]] | None = None

    @property
    def table(self) -> pa.Table:
        """Return the underlying PyArrow Table."""
        return self._table

    def to_polars(self) -> pl.DataFrame:
        """Return as a Polars DataFrame with zero-copy memory handoff."""
        if self._polars is None:
            df = pl.from_arrow(self._table)
            if not isinstance(df, pl.DataFrame):
                raise TypeError(f"expected a Polars DataFrame, got {type(df).__name__}")
            self._polars = df
        return self._polars

    def to_dataframe(self) -> nw.DataFrame[Any]:
        """Return as a Narwhals DataFrame for multi-engine compatibility."""
        return nw.from_native(self.to_polars())

    @property
    def names_table(self) -> pa.Table | None:
        """The ``register_names`` dataset (alternate spellings and nicknames), if loaded."""
        return self._names_table

    @property
    def links_table(self) -> pa.Table | None:
        """The ``register_links`` dataset (external source links per person), if loaded."""
        return self._links_table

    @property
    def countries_table(self) -> pa.Table | None:
        """The ``register_countries`` dataset (ISO, IOC and FIFA codes), if loaded."""
        return self._countries_table

    @staticmethod
    def _person_key(person: "str | PlayerRecord") -> str:
        return person.key_person if isinstance(person, PlayerRecord) else str(person)

    @staticmethod
    def _rows_where(table: pa.Table | None, column: str, value: str) -> list[dict[str, Any]]:
        if table is None or column not in table.column_names:
            return []
        mask = pc.equal(table.column(column), pa.scalar(value, table.schema.field(column).type))
        rows: list[dict[str, Any]] = table.filter(pc.fill_null(mask, False)).to_pylist()
        return rows

    def names_for(self, person: "str | PlayerRecord") -> list[dict[str, Any]]:
        """``register_names`` rows of a person (a ``key_person`` or a record), possibly none.

        Upstream may re-use a ``key_person`` for another identity in a later release; these rows
        belong to the register of the same release.
        """
        return self._rows_where(self._names_table, "key_person", self._person_key(person))

    def links_for(self, person: "str | PlayerRecord") -> list[dict[str, Any]]:
        """``register_links`` rows (``source``, ``value``) of a person, possibly none."""
        return self._rows_where(self._links_table, "key_person", self._person_key(person))

    def country(self, code: str) -> dict[str, Any] | None:
        """The ``register_countries`` row whose ISO alpha-2/alpha-3, IOC or FIFA code is ``code``.

        Matching ignores case; ``NA`` is Namibia (data, not a missing value).
        """
        wanted = code.strip().upper()
        table = self._countries_table
        if table is None or not wanted:
            return None
        for column in ("key_iso_alpha2", "key_iso_alpha3", "key_ioc", "key_fifa"):
            if column in table.column_names:
                upper = pc.utf8_upper(table.column(column))
                hit = table.filter(pc.fill_null(pc.equal(upper, wanted), False))
                if hit.num_rows:
                    return dict(hit.to_pylist()[0])
        return None

    # -- id indexes -------------------------------------------------------------------------

    def _ids(self, id_type: PlayerIdType) -> dict[Any, int]:
        """``id value -> row`` for ``id_type``, built on first use from the non-null values."""
        index = self._id_index.get(id_type)
        if index is None:
            index = self._build_id_index(id_type)
            self._id_index[id_type] = index
        return index

    def _build_id_index(self, id_type: PlayerIdType) -> dict[Any, int]:
        if id_type.value not in self._table.column_names:
            return {}
        column = self._table.column(id_type.value)
        if id_type in _CASEFOLDED_IDS:
            column = pc.utf8_lower(column)
        valid = pc.is_valid(column)
        rows = pc.indices_nonzero(valid).to_pylist()
        values = pc.filter(column, valid).to_pylist()
        # reversed, so that when an id repeats the first row wins
        index = dict(zip(reversed(values), reversed(rows), strict=True))
        if len(index) != len(values):
            logger.warning(
                "chadwick register has %d repeated %s value(s); the first row of each is used",
                len(values) - len(index),
                id_type.value,
            )
        return index

    def _records(self, rows: list[int]) -> list[PlayerRecord]:
        """Records for ``rows``, in that order."""
        if not rows:
            return []
        taken = self._table.take(pa.array(rows, pa.int64()))
        return [PlayerRecord.from_row(r) for r in taken.to_pylist()]

    def resolve(
        self,
        *,
        mlbam: int | None = None,
        retro: str | None = None,
        bbref: str | None = None,
        fangraphs: int | None = None,
        uuid: str | None = None,
        person: str | None = None,
        bbref_minors: str | None = None,
        npb: int | None = None,
        wikidata: str | None = None,
    ) -> PlayerRecord | None:
        """Resolve a single player by any known identifier (the first given id that is found wins)."""
        given = (
            (PlayerIdType.MLBAM, mlbam),
            (PlayerIdType.RETRO, retro),
            (PlayerIdType.BBREF, bbref),
            (PlayerIdType.FANGRAPHS, fangraphs),
            (PlayerIdType.UUID, uuid),
            (PlayerIdType.PERSON, person),
            (PlayerIdType.BBREF_MINORS, bbref_minors),
            (PlayerIdType.NPB, npb),
            (PlayerIdType.WIKIDATA, wikidata),
        )
        for id_type, value in given:
            norm = _normalise_id(id_type, value)
            if norm is not None and (row := self._ids(id_type).get(norm)) is not None:
                return self._records([row])[0]
        return None

    def resolve_id(
        self,
        id_value: Any,
        from_type: PlayerIdType | str,
        to_type: PlayerIdType | str,
    ) -> Any | None:
        """Crosswalk from one identifier system to another (``None`` when the id is unknown).

        Both types may be a ``PlayerIdType`` or its name (``"key_mlbam"`` or ``"mlbam"``); an
        unknown type raises ``ValueError``.
        """
        source = _id_type(from_type)
        target = _id_type(to_type)
        norm = _normalise_id(source, id_value)
        if norm is None:
            return None
        row = self._ids(source).get(norm)
        if row is None or target.value not in self._table.column_names:
            return None
        return self._table.column(target.value)[row].as_py()

    # -- name search ------------------------------------------------------------------------

    def _names(self) -> pl.Series:
        """Lower-case ``first last`` of every row (computed once)."""
        if self._lower_names is None:
            first = pl.col("name_first").fill_null("")
            last = pl.col("name_last").fill_null("")
            self._lower_names = self.to_polars().select(
                pl.concat_str([first, last], separator=" ")
                .str.strip_chars()
                .str.to_lowercase()
                .alias("name")
            )["name"]
        return self._lower_names

    def _nickname_table(self) -> dict[str, tuple[str, ...]]:
        if self._nicknames is None:
            self._nicknames = learn_nicknames(self.to_polars())
        return self._nicknames

    def _alias_index(self) -> dict[str, list[int]]:
        """``"first last"`` aliases -> rows: ``names.csv`` spellings and each person's ``name_nick``."""
        if self._aliases is None:
            aliases: dict[str, list[int]] = {}
            by_person = self._ids(PlayerIdType.PERSON)

            def add(alias: str, row: int) -> None:
                rows = aliases.setdefault(alias, [])
                if row not in rows:
                    rows.append(row)

            if self._names_table is not None:
                for entry in self._names_table.to_pylist():
                    row = by_person.get(entry.get("key_person"))
                    last = (entry.get("altname_last") or entry.get("name_last") or "").strip()
                    if row is None or not last:
                        continue
                    for column in ("altname_first", "altname_given", "name_first", "altname_nick"):
                        first = (entry.get(column) or "").strip()
                        if first:
                            add(f"{first} {last}".lower(), row)
            if "name_nick" in self._table.column_names:
                positions = pc.indices_nonzero(pc.is_valid(self._table.column("name_nick")))
                rows = positions.to_pylist()
                taken = self._table.take(pa.array(rows, pa.int64())).to_pylist() if rows else []
                for row, entry in zip(rows, taken, strict=True):
                    nick = (entry.get("name_nick") or "").strip()
                    last = (entry.get("name_last") or "").strip()
                    if nick and last:
                        add(f"{nick} {last}".lower(), row)
            self._aliases = aliases
        return self._aliases

    def search_name(
        self,
        name: str,
        fuzzy: bool = False,
        min_score: float = 0.9,
    ) -> list[PlayerRecord]:
        """Search players by name, nickname variants, and optional fuzzy matching.

        Tried in order, the first step that finds anyone answers: exact ``first last``; aliases
        (``names.csv`` spellings and a person's own ``name_nick``); nickname variants of the first
        name learned from the register (Pete, Peter); substring; and, with ``fuzzy=True``, the ten
        most Jaro-Winkler-similar names scoring at least ``min_score`` (default 0.9, about as strict as the old difflib 0.8).
        """
        clean = name.strip().lower()
        if not clean:
            return []
        names = self._names()

        if rows := names.eq(clean).arg_true().to_list():
            return self._records(rows)

        if rows := self._alias_index().get(clean, []):
            return self._records(rows)

        parts = clean.split()
        if len(parts) >= 2:
            first_name, last_name = parts[0], " ".join(parts[1:])
            for alt_first in self._nickname_table().get(first_name, ()):
                if rows := names.eq(f"{alt_first} {last_name}").arg_true().to_list():
                    return self._records(rows)

        if rows := names.str.contains(clean, literal=True).arg_true().to_list():
            return self._records(rows)

        if fuzzy:
            best = top_matches(names.to_arrow(), clean, min_score=min_score, limit=FUZZY_LIMIT)
            return self._records([row for row, _ in best])

        return []

    def __len__(self) -> int:
        return len(self._table)

    @classmethod
    def clear_cache(cls) -> None:
        """Forget the registers kept for this process (tests, or after changing the lake)."""
        _LOADED.clear()

    @classmethod
    def load(
        cls,
        refresh: bool = False,
        cache_config: LakeConfig | None = None,
    ) -> "ChadwickRegister":
        """Load the register, downloading and typing it first if the lake does not have it.

        The loaded register is kept for the process and reused until the Chadwick time-to-live has
        passed, the lake changes (a new ingest) or ``refresh=True``; so calling this (or
        ``crosswalk`` and ``resolve_player``) in a loop costs nothing after the first call.
        """
        catalog.register_all()
        config = cache_config or LakeConfig()
        key = (str(config.home), _lake_stamp(config))
        kept = _LOADED.get(key)
        ttl = config.ttl_for("chadwick")
        if not refresh and kept is not None and (ttl is None or time.monotonic() - kept[0] < ttl):
            return kept[1]
        store = ProcessedStore(config)
        outcome = ingest(
            refresh=refresh, config=config, extractor=ChadwickExtractor(cache_config=config)
        )
        tables: dict[str, pa.Table | None] = {}
        for name in ("register", "register_names", "register_links", "register_countries"):
            spec = get_dataset("chadwick", name)
            table = outcome.tables.get(name)
            if table is None and (name == "register" or store.is_cached(spec)):
                table = store.read_part(spec)
            tables[name] = table
        register_table = tables["register"]
        if register_table is None:
            raise RuntimeError("the Chadwick register dataset could not be loaded")
        register = cls(
            register_table,
            names_table=tables["register_names"],
            links_table=tables["register_links"],
            countries_table=tables["register_countries"],
        )
        _LOADED[(str(config.home), _lake_stamp(config))] = (time.monotonic(), register)
        return register
