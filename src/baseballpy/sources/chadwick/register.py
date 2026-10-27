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
    key_npb: str | None = None
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


def _read_links(raw: bytes) -> list[dict[str, str | None]]:
    """Parse links.csv rows (key_person, link_type, link_url) as strings; unknown cols dropped."""
    import csv
    import io

    wanted = ("key_person", "link_type", "link_url")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8", errors="replace"), newline=""))
    return [{k: (row.get(k) or None) for k in wanted} for row in reader]


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
        self._by_mlbam: dict[int, PlayerRecord] = {}
        self._by_retro: dict[str, PlayerRecord] = {}
        self._by_bbref: dict[str, PlayerRecord] = {}
        self._by_fangraphs: dict[int, PlayerRecord] = {}
        self._by_person: dict[str, PlayerRecord] = {}
        self._by_uuid: dict[str, PlayerRecord] = {}
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

            if rec.key_person:
                self._by_person[rec.key_person] = rec
            if rec.key_uuid:
                self._by_uuid[rec.key_uuid] = rec
            if mlbam is not None:
                self._by_mlbam[mlbam] = rec
            if retro:
                self._by_retro[retro.lower()] = rec
            if bbref:
                self._by_bbref[bbref.lower()] = rec
            if fangraphs is not None:
                self._by_fangraphs[fangraphs] = rec

            name_key = rec.full_name.lower()
            if name_key:
                self._by_name.setdefault(name_key, []).append(rec)

        # Index names.csv alternate spellings if available
        if self._names_table is not None:
            ndict = self._names_table.to_pydict()
            for i in range(len(self._names_table)):
                pid = ndict["key_person"][i]
                first = (ndict["name_first"][i] or "").strip().lower()
                last = (ndict["name_last"][i] or "").strip().lower()
                nick = (ndict["name_nick"][i] or "").strip().lower()
                full_alias = f"{first} {last}".strip()
                if pid and full_alias:
                    self._aliases.setdefault(full_alias, set()).add(pid)
                if pid and nick and last:
                    self._aliases.setdefault(f"{nick} {last}".strip(), set()).add(pid)

    def resolve(
        self,
        *,
        mlbam: int | None = None,
        retro: str | None = None,
        bbref: str | None = None,
        fangraphs: int | None = None,
        uuid: str | None = None,
        person: str | None = None,
    ) -> PlayerRecord | None:
        """Resolve a single player by any known identifier."""
        if mlbam is not None:
            return self._by_mlbam.get(mlbam)
        if retro is not None:
            return self._by_retro.get(retro.lower())
        if bbref is not None:
            return self._by_bbref.get(bbref.lower())
        if fangraphs is not None:
            return self._by_fangraphs.get(fangraphs)
        if uuid is not None:
            return self._by_uuid.get(uuid)
        if person is not None:
            return self._by_person.get(person)
        return None

    def resolve_id(
        self,
        id_value: Any,
        from_type: PlayerIdType | str,
        to_type: PlayerIdType | str,
    ) -> Any | None:
        """Crosswalk from one identifier system to another."""
        from_str = str(from_type).lower()
        to_str = str(to_type).lower()

        # 1. Resolve source player record
        record: PlayerRecord | None = None
        if "mlbam" in from_str:
            record = self._by_mlbam.get(int(id_value))
        elif "retro" in from_str:
            record = self._by_retro.get(str(id_value).lower())
        elif "bbref" in from_str:
            record = self._by_bbref.get(str(id_value).lower())
        elif "fangraphs" in from_str:
            record = self._by_fangraphs.get(int(id_value))
        elif "uuid" in from_str:
            record = self._by_uuid.get(str(id_value))
        elif "person" in from_str:
            record = self._by_person.get(str(id_value))

        if not record:
            return None

        # 2. Extract requested target identifier
        if "mlbam" in to_str:
            return record.key_mlbam
        if "retro" in to_str:
            return record.key_retro
        if "bbref" in to_str:
            return record.key_bbref
        if "fangraphs" in to_str:
            return record.key_fangraphs
        if "uuid" in to_str:
            return record.key_uuid
        if "person" in to_str:
            return record.key_person
        if "npb" in to_str:
            return record.key_npb
        if "wikidata" in to_str:
            return record.key_wikidata
        return None

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
            matched = [self._by_person[pid] for pid in pids if pid in self._by_person]
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
        names_spec = get_dataset("chadwick", "names")
        links_spec = get_dataset("chadwick", "links")

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

        # Persist as typed Parquet in processed/
        if config.enabled and len(table) > 0:
            ref = (extractor.manifest.get_chunk("commit_sha") or {}).get("sha") or None
            store.put(register_spec, table, source_ref=ref)
            if names_table is not None and len(names_table) > 0:
                store.put(names_spec, names_table, source_ref=ref)
            if "links.csv" in raw_shards:
                links = pa.Table.from_pylist(
                    list(_read_links(raw_shards["links.csv"])), schema=links_spec.schema
                )
                if len(links) > 0:
                    store.put(links_spec, links, source_ref=ref)

        return cls(table, names_table=names_table)
