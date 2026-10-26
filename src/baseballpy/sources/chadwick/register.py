"""Chadwick Bureau Player Register and fast in-memory lookup index."""

from dataclasses import dataclass
from typing import Any

import narwhals as nw
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.config import CacheConfig
from baseballpy.sources.chadwick.extractor import ChadwickExtractor
from baseballpy.sources.chadwick.normalizer import ChadwickNormalizer


@dataclass(frozen=True, slots=True)
class PlayerRecord:
    """Strongly-typed player identifier crosswalk record."""

    key_person: str
    key_uuid: str
    key_mlbam: int | None
    key_retro: str | None
    key_bbref: str | None
    key_fangraphs: int | None
    name_last: str | None
    name_first: str | None
    name_given: str | None
    birth_year: int | None
    birth_month: int | None
    birth_day: int | None
    mlb_played_first: int | None
    mlb_played_last: int | None

    @property
    def full_name(self) -> str:
        """Formatted full player name."""
        first = self.name_first or ""
        last = self.name_last or ""
        return f"{first} {last}".strip()


class ChadwickRegister:
    """Indexed player identity register for instant cross-system resolution."""

    def __init__(self, table: pa.Table) -> None:
        self._table = table
        self._records: list[PlayerRecord] = []
        self._by_mlbam: dict[int, PlayerRecord] = {}
        self._by_retro: dict[str, PlayerRecord] = {}
        self._by_bbref: dict[str, PlayerRecord] = {}
        self._by_fangraphs: dict[int, PlayerRecord] = {}
        self._by_person: dict[str, PlayerRecord] = {}
        self._by_name: dict[str, list[PlayerRecord]] = {}
        self._build_index()

    @property
    def table(self) -> pa.Table:
        """Return the underlying PyArrow Table."""
        return self._table

    def to_polars(self) -> pl.DataFrame:
        """Return as a Polars DataFrame with zero-copy memory handoff."""
        df = pl.from_arrow(self._table)
        assert isinstance(df, pl.DataFrame)
        return df

    def to_dataframe(self) -> nw.DataFrame[Any]:
        """Return as a Narwhals DataFrame for multi-engine compatibility."""
        return nw.from_native(self.to_polars())

    def _build_index(self) -> None:
        """Construct fast dictionary hash lookups from Arrow table."""
        # Convert to dictionary of Python objects for row instantiation
        pydict = self._table.to_pydict()
        length = len(self._table)

        for i in range(length):
            rec = PlayerRecord(
                key_person=pydict["key_person"][i],
                key_uuid=pydict["key_uuid"][i],
                key_mlbam=pydict["key_mlbam"][i],
                key_retro=pydict["key_retro"][i],
                key_bbref=pydict["key_bbref"][i],
                key_fangraphs=pydict["key_fangraphs"][i],
                name_last=pydict["name_last"][i],
                name_first=pydict["name_first"][i],
                name_given=pydict["name_given"][i],
                birth_year=pydict["birth_year"][i],
                birth_month=pydict["birth_month"][i],
                birth_day=pydict["birth_day"][i],
                mlb_played_first=pydict["mlb_played_first"][i],
                mlb_played_last=pydict["mlb_played_last"][i],
            )
            self._records.append(rec)
            self._by_person[rec.key_person] = rec

            if rec.key_mlbam is not None:
                self._by_mlbam[rec.key_mlbam] = rec
            if rec.key_retro is not None:
                self._by_retro[rec.key_retro.lower()] = rec
            if rec.key_bbref is not None:
                self._by_bbref[rec.key_bbref.lower()] = rec
            if rec.key_fangraphs is not None:
                self._by_fangraphs[rec.key_fangraphs] = rec

            # Index by normalized name
            if rec.full_name:
                name_key = rec.full_name.lower()
                self._by_name.setdefault(name_key, []).append(rec)

    def resolve(
        self,
        *,
        mlbam: int | None = None,
        retro: str | None = None,
        bbref: str | None = None,
        fangraphs: int | None = None,
        person: str | None = None,
    ) -> PlayerRecord | None:
        """Resolve a single player by known unique ID."""
        if mlbam is not None:
            return self._by_mlbam.get(mlbam)
        if retro is not None:
            return self._by_retro.get(retro.lower())
        if bbref is not None:
            return self._by_bbref.get(bbref.lower())
        if fangraphs is not None:
            return self._by_fangraphs.get(fangraphs)
        if person is not None:
            return self._by_person.get(person)
        return None

    def search_name(self, name: str) -> list[PlayerRecord]:
        """Search for players by full name (case-insensitive)."""
        clean = name.strip().lower()
        if exact := self._by_name.get(clean):
            return exact

        # Substring search if not exact match
        return [r for r in self._records if clean in r.full_name.lower()]

    def __len__(self) -> int:
        return len(self._records)

    @classmethod
    def load(
        cls,
        refresh: bool = False,
        cache_config: CacheConfig | None = None,
    ) -> "ChadwickRegister":
        """Load the register from local Parquet cache or download from GitHub."""
        config = cache_config or CacheConfig()
        parquet_path = config.chadwick_dir / "people.parquet"

        if not refresh and parquet_path.exists():
            table = pq.read_table(parquet_path)
            return cls(table)

        # Extract and normalize
        extractor = ChadwickExtractor(cache_config=config)
        normalizer = ChadwickNormalizer()
        raw_csv = extractor.extract(refresh=refresh)
        table = normalizer.normalize(raw_csv)

        # Cache as Parquet
        if config.enabled:
            pq.write_table(table, parquet_path, compression="snappy")

        return cls(table)
