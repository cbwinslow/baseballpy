"""Chadwick Bureau Player Register and fast in-memory lookup index with crosswalk resolution."""

import difflib
from dataclasses import dataclass
from typing import Any

import narwhals as nw
import polars as pl
import pyarrow as pa

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.stores import ProcessedStore
from baseballpy.sources import catalog
from baseballpy.sources.chadwick.extractor import ChadwickExtractor
from baseballpy.sources.chadwick.normalizer import ChadwickNormalizer
from baseballpy.sources.chadwick.schema import PlayerIdType

#: ``PlayerIdType.value`` is the register column and the ``PlayerRecord`` field; these sets say how
#: an id of that type is compared (integers are coerced, some text ids ignore case).
_INT_IDS = frozenset({PlayerIdType.MLBAM, PlayerIdType.FANGRAPHS, PlayerIdType.NPB})
_CASEFOLDED_IDS = frozenset({PlayerIdType.RETRO, PlayerIdType.BBREF, PlayerIdType.BBREF_MINORS})
_ID_TYPES = {id_type.value: id_type for id_type in PlayerIdType}


def _id_type(value: PlayerIdType | str) -> PlayerIdType:
    """The ``PlayerIdType`` for an enum member, ``"key_mlbam"`` or ``"mlbam"``."""
    text = str(value).lower()
    for candidate in (text, f"key_{text}"):
        if candidate in _ID_TYPES:
            return _ID_TYPES[candidate]
    raise ValueError(f"unknown player id type {value!r}; known: {sorted(_ID_TYPES)}")


def _normalise_id(id_type: PlayerIdType, value: Any) -> Any:
    """The form in which ``value`` is stored in and looked up from the index of ``id_type``."""
    if id_type in _INT_IDS:
        return int(value)
    text = str(value)
    return text.lower() if id_type in _CASEFOLDED_IDS else text


@dataclass(frozen=True, slots=True)
class PlayerRecord:
    """Strongly-typed player identifier crosswalk record."""

    key_person: str
    key_uuid: str
    key_mlbam: int | None
    key_retro: str | None
    key_bbref: str | None
    key_bbref_minors: str | None = None
    key_fangraphs: int | None = None
    key_npb: int | None = None
    key_wikidata: str | None = None
    name_last: str | None = None
    name_first: str | None = None
    name_given: str | None = None
    name_suffix: str | None = None
    name_nick: str | None = None
    birth_year: int | None = None
    birth_month: int | None = None
    birth_day: int | None = None
    mlb_played_first: int | None = None
    mlb_played_last: int | None = None

    @property
    def full_name(self) -> str:
        """Formatted full player name."""
        first = self.name_first or ""
        last = self.name_last or ""
        return f"{first} {last}".strip()


# Common baseball nicknames mapping to formal first names
COMMON_NICKNAMES: dict[str, list[str]] = {
    "pete": ["peter"],
    "peter": ["pete"],
    "mike": ["michael"],
    "michael": ["mike"],
    "bob": ["robert"],
    "bobby": ["robert"],
    "rob": ["robert"],
    "robert": ["bob", "bobby", "rob"],
    "bill": ["william"],
    "billy": ["william"],
    "will": ["william"],
    "william": ["bill", "billy", "will"],
    "jim": ["james"],
    "jimmy": ["james"],
    "james": ["jim", "jimmy"],
    "dan": ["daniel"],
    "danny": ["daniel"],
    "daniel": ["dan", "danny"],
    "tom": ["thomas"],
    "tommy": ["thomas"],
    "thomas": ["tom", "tommy"],
    "joe": ["joseph"],
    "joseph": ["joe"],
    "tony": ["anthony"],
    "anthony": ["tony"],
    "chris": ["christopher"],
    "christopher": ["chris"],
    "matt": ["matthew"],
    "matthew": ["matt"],
    "alex": ["alexander"],
    "alexander": ["alex"],
    "nick": ["nicholas"],
    "nicholas": ["nick"],
    "dave": ["david"],
    "david": ["dave"],
    "ken": ["kenneth"],
    "kenny": ["kenneth"],
    "kenneth": ["ken", "kenny"],
    "ron": ["ronald"],
    "ronnie": ["ronald"],
    "ronald": ["ron", "ronnie"],
    "ed": ["edward", "edwin"],
    "eddie": ["edward", "edwin"],
    "edward": ["ed", "eddie"],
    "edwin": ["ed", "eddie"],
    "frank": ["francis", "franklin"],
    "frankie": ["francis", "franklin"],
    "steve": ["stephen", "steven"],
    "steven": ["steve"],
    "stephen": ["steve"],
    "sam": ["samuel"],
    "sammy": ["samuel"],
    "samuel": ["sam", "sammy"],
    "fred": ["frederick"],
    "freddie": ["frederick"],
    "frederick": ["fred", "freddie"],
    "dick": ["richard"],
    "rich": ["richard"],
    "richie": ["richard"],
    "rick": ["richard"],
    "ricky": ["richard"],
    "richard": ["dick", "rich", "richie", "rick", "ricky"],
    "babe": ["george"],
    "chipper": ["larry"],
    "buster": ["gerald"],
    "shohei": ["shohei"],
}


class ChadwickRegister:
    """Indexed player identity register for instant cross-system resolution."""

    def __init__(
        self,
        table: pa.Table,
        names_table: pa.Table | None = None,
    ) -> None:
        self._table = table
        self._names_table = names_table
        self._records: list[PlayerRecord] = []
        self._by_id: dict[PlayerIdType, dict[Any, PlayerRecord]] = {t: {} for t in PlayerIdType}
        self._by_name: dict[str, list[PlayerRecord]] = {}
        self._aliases: dict[str, set[str]] = {}
        self._build_index()

    @property
    def table(self) -> pa.Table:
        """Return the underlying PyArrow Table."""
        return self._table

    def to_polars(self) -> pl.DataFrame:
        """Return as a Polars DataFrame with zero-copy memory handoff."""
        df = pl.from_arrow(self._table)
        if not isinstance(df, pl.DataFrame):
            raise TypeError(f"expected a Polars DataFrame, got {type(df).__name__}")
        return df

    def to_dataframe(self) -> nw.DataFrame[Any]:
        """Return as a Narwhals DataFrame for multi-engine compatibility."""
        return nw.from_native(self.to_polars())

    def _build_index(self) -> None:
        """Construct fast dictionary hash lookups from Arrow table."""
        pydict = self._table.to_pydict()
        length = len(self._table)

        col_names = self._table.column_names
        for i in range(length):
            mlbam = pydict["key_mlbam"][i]
            retro = pydict["key_retro"][i]
            bbref = pydict["key_bbref"][i]
            fangraphs = pydict["key_fangraphs"][i] if "key_fangraphs" in col_names else None
            bbref_min = pydict["key_bbref_minors"][i] if "key_bbref_minors" in col_names else None
            npb = pydict["key_npb"][i] if "key_npb" in col_names else None
            wiki = pydict["key_wikidata"][i] if "key_wikidata" in col_names else None
            suffix = pydict["name_suffix"][i] if "name_suffix" in col_names else None
            nick = pydict["name_nick"][i] if "name_nick" in col_names else None

            rec = PlayerRecord(
                key_person=pydict["key_person"][i],
                key_uuid=pydict["key_uuid"][i],
                key_mlbam=mlbam,
                key_retro=retro,
                key_bbref=bbref,
                key_bbref_minors=bbref_min,
                key_fangraphs=fangraphs,
                key_npb=npb,
                key_wikidata=wiki,
                name_last=pydict["name_last"][i],
                name_first=pydict["name_first"][i],
                name_given=pydict["name_given"][i],
                name_suffix=suffix,
                name_nick=nick,
                birth_year=pydict["birth_year"][i],
                birth_month=pydict["birth_month"][i],
                birth_day=pydict["birth_day"][i],
                mlb_played_first=pydict["mlb_played_first"][i],
                mlb_played_last=pydict["mlb_played_last"][i],
            )
            self._records.append(rec)

            for id_type, index in self._by_id.items():
                value = getattr(rec, id_type.value)
                if value is not None and value != "":
                    index[_normalise_id(id_type, value)] = rec

            name_key = rec.full_name.lower()
            if name_key:
                self._by_name.setdefault(name_key, []).append(rec)

        # Index names.csv alternate spellings if available
        if self._names_table is not None:
            ndict = self._names_table.to_pydict()
            for i in range(len(self._names_table)):
                pid = ndict["key_person"][i]
                if not pid:
                    continue
                last = (ndict["altname_last"][i] or ndict["name_last"][i] or "").strip().lower()
                for first_col in ("altname_first", "altname_given", "name_first"):
                    first = (ndict[first_col][i] or "").strip().lower()
                    if first and last:
                        self._aliases.setdefault(f"{first} {last}", set()).add(pid)
                nick = (ndict["altname_nick"][i] or "").strip().lower()
                if nick and last:
                    self._aliases.setdefault(f"{nick} {last}", set()).add(pid)

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
        """Resolve a single player by any known identifier (the first one given wins)."""
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
            if value is not None:
                return self._by_id[id_type].get(_normalise_id(id_type, value))
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
        record = self._by_id[source].get(_normalise_id(source, id_value))
        return None if record is None else getattr(record, target.value)

    def search_name(
        self,
        name: str,
        fuzzy: bool = False,
        min_score: float = 0.8,
    ) -> list[PlayerRecord]:
        """Search players by name, nickname variants, and optional fuzzy matching."""
        clean = name.strip().lower()
        if not clean:
            return []

        # 1. Exact match
        if exact := self._by_name.get(clean):
            return exact

        # 2. Check alias index from names.csv
        if pids := self._aliases.get(clean):
            by_person = self._by_id[PlayerIdType.PERSON]
            matched = [by_person[pid] for pid in pids if pid in by_person]
            if matched:
                return matched

        # 3. Nickname expansion (e.g. Pete Alonso -> Peter Alonso)
        parts = clean.split()
        if len(parts) >= 2:
            first_name, last_name = parts[0], " ".join(parts[1:])
            if variants := COMMON_NICKNAMES.get(first_name):
                for alt_first in variants:
                    alt_key = f"{alt_first} {last_name}"
                    if alt_matches := self._by_name.get(alt_key):
                        return alt_matches

        # 4. Substring search
        substr_matches = [r for r in self._records if clean in r.full_name.lower()]
        if substr_matches:
            return substr_matches

        # 5. Fuzzy string similarity if requested
        if fuzzy:
            scored: list[tuple[float, PlayerRecord]] = []
            for r in self._records:
                score = difflib.SequenceMatcher(None, clean, r.full_name.lower()).ratio()
                if score >= min_score:
                    scored.append((score, r))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [r for _, r in scored[:10]]

        return []

    def __len__(self) -> int:
        return len(self._records)

    @classmethod
    def load(
        cls,
        refresh: bool = False,
        cache_config: LakeConfig | None = None,
    ) -> "ChadwickRegister":
        """Load register from local Parquet cache or extract from GitHub shards."""
        catalog.register_all()
        config = cache_config or LakeConfig()
        store = ProcessedStore(config)
        register_spec = get_dataset("chadwick", "register")
        names_spec = get_dataset("chadwick", "register_names")
        links_spec = get_dataset("chadwick", "register_links")
        countries_spec = get_dataset("chadwick", "register_countries")

        extractor = ChadwickExtractor(cache_config=config)
        if not refresh and store.is_cached(register_spec) and extractor.is_cache_current(False):
            table = store.read_part(register_spec)
            names_table = store.read_part(names_spec) if store.is_cached(names_spec) else None
            return cls(table, names_table=names_table)

        # Extract and normalize
        normalizer = ChadwickNormalizer()
        raw_shards = extractor.extract(refresh=refresh)
        table = normalizer.normalize(raw_shards)

        names_table = None
        if "names.csv" in raw_shards:
            names_table = normalizer.normalize_names(raw_shards["names.csv"])
        links_table = (
            normalizer.normalize_links(raw_shards["links.csv"])
            if "links.csv" in raw_shards
            else None
        )
        countries_table = (
            normalizer.normalize_countries(raw_shards["countries.csv"])
            if "countries.csv" in raw_shards
            else None
        )

        # Persist as typed Parquet in processed/
        if config.enabled and len(table) > 0:
            ref = (extractor.manifest.get_chunk("commit_sha") or {}).get("sha") or None
            store.put(register_spec, table, source_ref=ref)
            if names_table is not None and len(names_table) > 0:
                store.put(names_spec, names_table, source_ref=ref)
            for spec, aux in ((links_spec, links_table), (countries_spec, countries_table)):
                if aux is not None and len(aux) > 0:
                    store.put(spec, aux, source_ref=ref)

        return cls(table, names_table=names_table)
