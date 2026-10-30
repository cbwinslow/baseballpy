"""High-level Retrosheet extraction, parsing and ingest interface (lake layout v2).

Parsing streams: each upstream file is parsed to one Arrow table (optionally in a bounded process
pool) and the tables are written as row groups of one atomic Parquet part per dataset and season.
Every dataset the pinned tree offers can be ingested with :meth:`RetrosheetSource.ingest_all`,
which resumes after interruption because completed chunks are recorded in manifests.
"""

import hashlib
import logging
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec, datasets_for, get_dataset
from baseballpy.core.github_tree import TreeTruncatedError
from baseballpy.core.http import HttpStatusError, TransportError
from baseballpy.core.lazy import lazy_singleton
from baseballpy.core.stores import ProcessedStore, manifest_key
from baseballpy.core.upstream import Fingerprint, stored_fingerprint
from baseballpy.sources import catalog
from baseballpy.sources.retrosheet.box_parser import decode_box, parse_box_text
from baseballpy.sources.retrosheet.downloader import RetrosheetDownloader
from baseballpy.sources.retrosheet.pool import parse_stream
from baseballpy.sources.retrosheet.quality import columns_needed, quality_report
from baseballpy.sources.retrosheet.tree import POSTSEASON_GAMELOG_KINDS, RetroFile

logger = logging.getLogger(__name__)

#: fingerprint kind of a processed chunk: a digest of the git blob SHAs of the raw files it was built from
INPUT_SET = "input_set"

#: ingest unit -> (raw file kinds it reads, (dataset, chunk id) pairs it writes; ``{y}`` is the season)
UNITS: dict[str, tuple[tuple[str, ...], tuple[tuple[str, str], ...]]] = {
    "events": (("team", "event_regular"), (("events", "events"),)),
    "events_postseason": (("team", "event_postseason"), (("events_postseason", "events"),)),
    "events_deduced": (("team", "event_deduced"), (("events_deduced", "events"),)),
    "boxscores": (
        ("team", "event_regular"),
        (("boxscores_batting", "batting"), ("boxscores_pitching", "pitching")),
    ),
    "box_accounts": (
        ("box",),
        tuple(
            (name, "box_{y}")
            for name in ("box_games", "box_starters", "box_batting_lines", "box_records")
        ),
    ),
    "daily_splits": (("team", "event_regular"), (("daily_splits", "daily_splits"),)),
    "substitutions": (("team", "event_regular"), (("substitutions", "substitutions"),)),
    "rosters": (("roster",), (("rosters", "rosters_{y}"),)),
    "gamelogs": (("gamelog",), (("gamelogs", "gl{y}"),)),
    "schedule": (("schedule",), (("schedule", "schedule_{y}"),)),
    "schedule_original": (
        ("schedule_original",),
        (("schedule_original", "schedule_original_{y}"),),
    ),
    "umpires": (("umpires",), (("umpires", "umpires_{y}"),)),
    "discrepancies": (("discrepancies",), (("discrepancies", "discrepancies_{y}"),)),
}

#: season-partitioned ingest units in the order :meth:`RetrosheetSource.ingest_season` writes them
SEASON_DATASETS = tuple(UNITS)

#: unit that ingests the season-less datasets (every ``reference/*.csv`` and the postseason game logs)
REFERENCE_UNIT = "reference"

#: registry dataset name -> the ingest unit that writes it (pinned to the registry by a test)
DATASET_UNIT: dict[str, str] = {
    dataset: unit for unit, (_, outputs) in UNITS.items() for dataset, _ in outputs
}

BOX_DATASETS = ("box_games", "box_starters", "box_batting_lines", "box_records")

#: unit -> (parse kind of ``pool.parse_stream``, raw file kind the parser reads)
PARSE: dict[str, tuple[str, str]] = {
    "events": ("events", "event_regular"),
    "events_postseason": ("events", "event_postseason"),
    "events_deduced": ("events", "event_deduced"),
    "daily_splits": ("daily_splits", "event_regular"),
    "substitutions": ("substitutions", "event_regular"),
    "rosters": ("rosters", "roster"),
    "gamelogs": ("gamelogs", "gamelog"),
    "schedule": ("flat:schedule", "schedule"),
    "schedule_original": ("flat:schedule_original", "schedule_original"),
    "umpires": ("flat:umpires", "umpires"),
    "discrepancies": ("flat:discrepancies", "discrepancies"),
}


def unit_of(name: str) -> str | None:
    """The ingest unit a unit name or registry dataset name belongs to (``None`` = unknown)."""
    if name in UNITS or name == REFERENCE_UNIT:
        return name
    if name in DATASET_UNIT:
        return DATASET_UNIT[name]
    if name == "gamelogs_postseason" or name.startswith("reference_"):
        catalog.register_all()
        try:
            _spec(name)
        except KeyError:
            return None
        return REFERENCE_UNIT
    return None


def units_for(names: Sequence[str]) -> tuple[str, ...]:
    """Ingest units for unit or registry names, in order without repeats; unknown names are kept."""
    return tuple(dict.fromkeys(unit_of(n) or n for n in names))


#: registry dataset -> (public accessor, index of the table in its result; ``None`` = the result is the table)
ACCESSORS: dict[str, tuple[str, int | str | None]] = {
    "events": ("events", None),
    "events_postseason": ("events_postseason", None),
    "events_deduced": ("events_deduced", None),
    "boxscores_batting": ("boxscores", 0),
    "boxscores_pitching": ("boxscores", 1),
    "box_games": ("box_accounts", "box_games"),
    "box_starters": ("box_accounts", "box_starters"),
    "box_batting_lines": ("box_accounts", "box_batting_lines"),
    "box_records": ("box_accounts", "box_records"),
    "daily_splits": ("daily_splits", None),
    "substitutions": ("substitutions", None),
    "rosters": ("rosters", None),
    "gamelogs": ("game_logs", None),
    "schedule": ("schedule", None),
    "schedule_original": ("schedule_original", None),
    "umpires": ("umpires", None),
    "discrepancies": ("discrepancies", None),
}


def _tables(stream: Iterator[pa.Table | tuple[pa.Table, pa.Table]]) -> Iterator[pa.Table]:
    """Narrow a parse stream to plain tables (a pair here is a programming error)."""
    for item in stream:
        if not isinstance(item, pa.Table):
            raise TypeError(f"expected one table per file, got {type(item).__name__}")
        yield item


def _pair(item: pa.Table | tuple[pa.Table, pa.Table]) -> tuple[pa.Table, pa.Table]:
    if isinstance(item, pa.Table):
        raise TypeError("expected a (batting, pitching) pair per file")
    return item


def _spec(name: str) -> DatasetSpec:
    return get_dataset("retrosheet", name)


@dataclass
class SeasonReport:
    """Rows written (or ``None`` when already cached) per dataset for one season."""

    year: int
    datasets: dict[str, int | None] = field(default_factory=dict)
    complete_download: bool = False
    error: str | None = None


@dataclass
class IngestReport:
    """Outcome of :meth:`RetrosheetSource.ingest_all`."""

    seasons: list[SeasonReport] = field(default_factory=list)
    reference: dict[str, int | None] = field(default_factory=dict)
    failures: dict[int, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True when no season failed."""
        return not self.failures


class RetrosheetSource:
    """Retrosheet dataset orchestrator: raw/ bytes, processed/ Parquet, pause/resume."""

    def __init__(self, cache_config: LakeConfig | None = None) -> None:
        catalog.register_all()
        self.cache_config = cache_config or LakeConfig()
        self.downloader = RetrosheetDownloader(cache_config=self.cache_config)
        self.store = ProcessedStore(self.cache_config)
        #: (season, file kind) pairs already re-downloaded by this object, so ``refresh`` fetches a file once
        self._refreshed: set[tuple[int, str]] = set()
        self._tree_warned = False
        self._register_loaded = False
        self._register_ids: pa.Table | None = None

    # ------------------------------------------------------------------ plumbing
    @property
    def _workers(self) -> int:
        return self.cache_config.parse_workers

    @property
    def _ref(self) -> str:
        return self.downloader.source_ref.ref

    def _inputs(self, unit: str, year: int | None) -> list[RetroFile] | None:
        """The raw files the unit's chunk is built from; ``None`` when the tree cannot be listed."""
        try:
            tree = self.downloader.tree()
        except (HttpStatusError, TransportError, ValueError, TreeTruncatedError) as exc:
            if not self._tree_warned:
                self._tree_warned = True
                logger.warning(
                    "retrosheet: cannot list the upstream tree (%s); cached data is judged by its pinned ref",
                    exc,
                )
            return None
        if year is None:
            return None
        return tree.season_files(year, UNITS[unit][0])

    @staticmethod
    def _expected(files: Sequence[RetroFile] | None) -> Fingerprint | None:
        """One fingerprint for a set of raw files: a digest of their git blob SHAs (ADR 48)."""
        if files is None or any(not f.sha for f in files):
            return None  # no tree to compare with, or a file the tree gave no blob SHA
        lines = sorted(f"{f.path}:{f.sha}" for f in files)
        return Fingerprint(INPUT_SET, hashlib.sha256("\n".join(lines).encode()).hexdigest())

    def _current(
        self, dataset: str, chunk_id: str, season: int | None, expected: Fingerprint | None
    ) -> bool:
        """Whether the stored chunk can be served: it exists and was built from these raw files.

        A chunk written before fingerprints existed (or when no tree is available) is judged by the
        pinned ref it was recorded at.
        """
        spec = _spec(dataset)
        if not self.store.is_cached(spec, chunk_id, season):
            return False
        manifest = self.cache_config.dataset_manifest("retrosheet", dataset, "processed")
        entry = manifest.get_chunk(manifest_key(chunk_id, season))
        if not entry:
            return False
        stored = stored_fingerprint(entry)
        if expected is not None and stored is not None and stored.kind == INPUT_SET:
            return stored.matches(expected)
        return entry.get("source_ref") in (None, self._ref)

    def _download(self, year: int, kinds: Sequence[str], refresh: bool) -> None:
        """Make the raw files of ``kinds`` present; with ``refresh`` each is re-fetched once per object."""
        if refresh:
            todo = [k for k in kinds if (year, k) not in self._refreshed]
            if todo:
                self.downloader.download_season(year, kinds=todo, refresh=True)
                self._refreshed.update((year, k) for k in todo)
        self.downloader.download_season(year, kinds=kinds)

    def _write(
        self,
        name: str,
        chunk_id: str,
        season: int | None,
        refresh: bool,
        batches: Callable[[], Iterator[pa.Table]],
        files: Sequence[RetroFile] | None = None,
    ) -> int | None:
        """Stream ``batches()`` into the dataset chunk unless it is already current.

        ``files`` are the raw files the chunk is built from (their blob SHAs become the chunk's
        fingerprint). Returns the rows written, or ``None`` when the chunk was already current.
        """
        spec = _spec(name)
        expected = self._expected(files)
        if not refresh and self._current(name, chunk_id, season, expected):
            return None
        if not self.cache_config.enabled:
            return int(sum(t.num_rows for t in batches()))
        rows: int = self.store.put_stream(
            spec,
            batches(),
            chunk_id=chunk_id,
            season=season,
            source_ref=self._ref,
            metadata={"upstream": expected.to_dict()} if expected is not None else None,
        )
        return rows

    def _read(
        self,
        name: str,
        chunk_id: str,
        season: int | None,
        refresh: bool,
        batches: Callable[[], Iterator[pa.Table]],
        files: Sequence[RetroFile] | None = None,
    ) -> pa.Table:
        """``_write`` then return the stored table (or the parsed one when caching is off)."""
        if not self.cache_config.enabled:
            tables = list(batches())
            return pa.concat_tables(tables) if tables else _spec(name).schema.empty_table()
        self._write(name, chunk_id, season, refresh, batches, files)
        return self.store.read_part(_spec(name), chunk_id, season)

    # ------------------------------------------------------------------ one declarative producer
    def _season_batches(
        self, unit: str, year: int, refresh: bool
    ) -> Callable[[], Iterator[pa.Table]]:
        """Download what the unit needs and parse it, one table per raw file."""
        parse, path_kind = PARSE[unit]

        def make() -> Iterator[pa.Table]:
            if unit == "gamelogs":
                self._download(year, UNITS[unit][0], refresh)
                paths = [self.downloader.download_gamelog(year)]
            else:
                self._download(year, UNITS[unit][0], refresh)
                paths = self.downloader.local_paths(year, path_kind)
            yield from _tables(parse_stream(parse, paths, year, self._workers))

        return make

    def _unit_table(self, unit: str, year: int, refresh: bool) -> pa.Table:
        """The stored table of a one-output unit, built first when it is not current."""
        dataset, chunk = UNITS[unit][1][0]
        return self._read(
            dataset,
            chunk.format(y=year),
            year,
            refresh,
            self._season_batches(unit, year, refresh),
            self._inputs(unit, year),
        )

    def _unit_write(self, unit: str, year: int, refresh: bool) -> dict[str, int | None]:
        """Build the chunks of a unit; rows written per dataset (``None`` = already current)."""
        with default_audit_logger.track(
            operation=f"retrosheet_build_{unit}",
            source="retrosheet",
            endpoint=f"{unit}:{year}",
            destination=str(self.cache_config.processed_root / "retrosheet"),
        ) as tracker:
            written = self._unit_build(unit, year, refresh)
            tracker.set_records(sum(n or 0 for n in written.values()))
            tracker.set_cache_hit(all(n is None for n in written.values()))
            return written

    def _unit_build(self, unit: str, year: int, refresh: bool) -> dict[str, int | None]:
        if unit == "boxscores":
            return self._boxscores_write(year, refresh)
        if unit == "box_accounts":
            return self._box_accounts_write(year, refresh)
        dataset, chunk = UNITS[unit][1][0]
        if unit == "gamelogs" and not self.downloader.tree().season_files(year, ["gamelog"]):
            # the tree lists no game log for this season (e.g. a future schedule-only year)
            chunk_id = chunk.format(y=year)
            if refresh or not self._current(dataset, chunk_id, year, None):
                self.store.put_stream(
                    _spec(dataset), iter(()), chunk_id=chunk_id, season=year, source_ref=self._ref
                )
                return {dataset: 0}
            return {dataset: None}
        rows = self._write(
            dataset,
            chunk.format(y=year),
            year,
            refresh,
            self._season_batches(unit, year, refresh),
            self._inputs(unit, year),
        )
        return {dataset: rows}

    # ------------------------------------------------------------------ event-file datasets
    def events(
        self, year: int, include_postseason: bool = False, refresh: bool = False
    ) -> pa.Table:
        """Typed play-by-play events of the regular season (``.EVA``/``.EVN`` files).

        ``include_postseason=True`` also returns the postseason/all-star events (a separate
        dataset, ``events_postseason``) concatenated after the regular-season rows.
        """
        regular = self._unit_table("events", year, refresh)
        if not include_postseason:
            return regular
        post = self.events_postseason(year, refresh)
        return (
            pa.concat_tables([regular, post], promote_options="permissive")
            if len(post)
            else regular
        )

    def events_postseason(self, year: int, refresh: bool = False) -> pa.Table:
        """Typed events of postseason, all-star and other special games (``.EVE/.EVR/.EVF``)."""
        return self._unit_table("events_postseason", year, refresh)

    def events_deduced(self, year: int, refresh: bool = False) -> pa.Table:
        """Typed events deduced from box scores (``.EDA/.EDN/.EDF`` files)."""
        return self._unit_table("events_deduced", year, refresh)

    def _boxscores_batches(self, year: int, refresh: bool) -> tuple[list[pa.Table], list[pa.Table]]:
        self._download(year, UNITS["boxscores"][0], refresh)
        paths = self.downloader.local_paths(year, "event_regular")
        batting: list[pa.Table] = []
        pitching: list[pa.Table] = []
        for pair in parse_stream("boxscores", paths, year, self._workers):
            bat, pit = _pair(pair)
            batting.append(bat)
            pitching.append(pit)
        return batting, pitching

    def _boxscores_write(self, year: int, refresh: bool) -> dict[str, int | None]:
        expected = self._expected(self._inputs("boxscores", year))
        outputs = UNITS["boxscores"][1]
        if not refresh and all(self._current(d, c, year, expected) for d, c in outputs):
            return {d: None for d, _ in outputs}
        batting, pitching = self._boxscores_batches(year, refresh)
        meta = {"upstream": expected.to_dict()} if expected is not None else None
        counts: dict[str, int | None] = {}
        for (dataset, chunk), tables in zip(outputs, (batting, pitching), strict=True):
            counts[dataset] = self.store.put_stream(
                _spec(dataset),
                iter(tables),
                chunk_id=chunk,
                season=year,
                source_ref=self._ref,
                metadata=meta,
            )
        return counts

    def boxscores(self, year: int, refresh: bool = False) -> tuple[pa.Table, pa.Table]:
        """Batting and pitching boxscores derived from the regular-season event files."""
        spec_b, spec_p = _spec("boxscores_batting"), _spec("boxscores_pitching")
        if not self.cache_config.enabled:
            batting, pitching = self._boxscores_batches(year, refresh)
            return (
                pa.concat_tables(batting) if batting else spec_b.schema.empty_table(),
                pa.concat_tables(pitching) if pitching else spec_p.schema.empty_table(),
            )
        self._boxscores_write(year, refresh)
        return (
            self.store.read_part(spec_b, "batting", year),
            self.store.read_part(spec_p, "pitching", year),
        )

    def _box_accounts_parsed(self, year: int, refresh: bool) -> dict[str, pa.Table]:
        self._download(year, UNITS["box_accounts"][0], refresh)
        parsed = [
            parse_box_text(decode_box(path.read_bytes()), path.name)
            for path in self.downloader.local_paths(year, "box")
        ]
        out: dict[str, pa.Table] = {}
        for name in BOX_DATASETS:
            parts = [t.by_name()[name] for t in parsed]
            out[name] = pa.concat_tables(parts) if parts else _spec(name).schema.empty_table()
        return out

    def _box_accounts_write(self, year: int, refresh: bool) -> dict[str, int | None]:
        expected = self._expected(self._inputs("box_accounts", year))
        outputs = UNITS["box_accounts"][1]
        if not refresh and all(
            self._current(d, c.format(y=year), year, expected) for d, c in outputs
        ):
            return {d: None for d, _ in outputs}
        tables = self._box_accounts_parsed(year, refresh)
        meta = {"upstream": expected.to_dict()} if expected is not None else None
        return {
            dataset: self.store.put_stream(
                _spec(dataset),
                iter([tables[dataset]]),
                chunk_id=chunk.format(y=year),
                season=year,
                source_ref=self._ref,
                metadata=meta,
            )
            for dataset, chunk in outputs
        }

    def box_accounts(self, year: int, refresh: bool = False) -> dict[str, pa.Table]:
        """Box-score game accounts (``.EBA/.EBN/.EBE/.EBR/.EBF``) as the four ``box_*`` datasets.

        Seasons whose games exist only as box accounts (many before 1920) have no play-by-play
        events; seasons without any ``.EB*`` file store empty tables so the views keep a schema.
        """
        if not self.cache_config.enabled:
            return self._box_accounts_parsed(year, refresh)
        self._box_accounts_write(year, refresh)
        chunk = f"box_{year}"
        return {n: self.store.read_part(_spec(n), chunk, year) for n in BOX_DATASETS}

    def daily_splits(self, year: int, refresh: bool = False) -> pa.Table:
        """Daily player appearance lines derived from the regular-season event files."""
        return self._unit_table("daily_splits", year, refresh)

    def substitutions(self, year: int, refresh: bool = False) -> pa.Table:
        """In-game substitutions derived from the regular-season event files."""
        return self._unit_table("substitutions", year, refresh)

    # ------------------------------------------------------------------ other season files
    def rosters(self, year: int, refresh: bool = False) -> pa.Table:
        """Team rosters (``*.ROS``) for a season."""
        return self._unit_table("rosters", year, refresh)

    def schedule(self, year: int, refresh: bool = False) -> pa.Table:
        """The season schedule (``<year>schedule.csv``), including future seasons when listed."""
        return self._unit_table("schedule", year, refresh)

    def schedule_original(self, year: int, refresh: bool = False) -> pa.Table:
        """The original (pre-disruption) schedule, e.g. 2020's ``2020sched-orig.csv``."""
        return self._unit_table("schedule_original", year, refresh)

    def umpires(self, year: int, refresh: bool = False) -> pa.Table:
        """Umpires of a season (``UMPIRES<year>.txt``)."""
        return self._unit_table("umpires", year, refresh)

    def discrepancies(self, year: int, refresh: bool = False) -> pa.Table:
        """Known data discrepancies of a season (AL/NL/federal ``*discs.csv`` files)."""
        return self._unit_table("discrepancies", year, refresh)

    def game_logs(self, year: int, refresh: bool = False) -> pa.Table:
        """The season's 161-column game log (``GL<year>.TXT``)."""
        return self._unit_table("gamelogs", year, refresh)

    def postseason_game_logs(self, kind: str, refresh: bool = False) -> pa.Table:
        """Postseason/all-star game logs (wild_card, division_series, lcs, world_series, all_star)."""

        def make() -> Iterator[pa.Table]:
            path = self.downloader.download_postseason_gamelog(kind, refresh=refresh)
            yield from _tables(parse_stream("gamelogs", [path], None, self._workers))

        file = (
            self.downloader.tree().postseason_gamelog(kind)
            if kind.lower() in POSTSEASON_GAMELOG_KINDS
            else None
        )
        return self._read(
            "gamelogs_postseason", kind.lower(), None, refresh, make, [file] if file else None
        )

    def reference(self, table_name: str, refresh: bool = False) -> pa.Table:
        """A ``reference/<name>.csv`` table (ballparks, teams, ejections, coaches, relatives, ...)."""
        dataset = f"reference_{table_name.lower()}"
        try:
            _spec(dataset)
        except KeyError:
            known = sorted(
                d.removeprefix("reference_")
                for d in (
                    f"reference_{f.name.removesuffix('.csv').lower()}"
                    for f in self.downloader.tree().reference
                )
            )
            raise ValueError(
                f"Unknown reference table '{table_name}'. Valid tables: {known}"
            ) from None

        def make() -> Iterator[pa.Table]:
            path = self.downloader.download_reference_table(table_name, refresh=refresh)
            yield from _tables(parse_stream(f"flat:{dataset}", [path], None, self._workers))

        file = self.downloader.tree().reference_file(table_name)
        return self._read(dataset, "data", None, refresh, make, [file] if file else None)

    def table(
        self,
        name: str,
        season: int | None = None,
        *,
        kind: str | None = None,
        refresh: bool = False,
    ) -> pa.Table:
        """Any registered Retrosheet dataset by its registry name (``baseballpy.sources.retrosheet.table``).

        Season datasets need ``season``; ``reference_*`` tables need nothing; ``gamelogs_postseason``
        takes an optional ``kind`` (``world_series``, ``lcs``, ...) and returns all kinds without it.
        """
        catalog.register_all()
        if name in ACCESSORS:
            if season is None:
                raise ValueError(
                    f"retrosheet dataset {name!r} is stored per season: pass season=YYYY"
                )
            method, pick = ACCESSORS[name]
            result = getattr(self, method)(season, refresh=refresh)
            return result if pick is None else result[pick]
        if name == "gamelogs_postseason":
            kinds = (
                [kind]
                if kind
                else [
                    k
                    for k in POSTSEASON_GAMELOG_KINDS
                    if self.downloader.tree().postseason_gamelog(k)
                ]
            )
            parts = [self.postseason_game_logs(k, refresh) for k in kinds]
            return pa.concat_tables(parts) if parts else _spec(name).schema.empty_table()
        if name.startswith("reference_"):
            return self.reference(name.removeprefix("reference_"), refresh)
        known = sorted(
            {*DATASET_UNIT, "gamelogs_postseason"} | {d.name for d in datasets_for("retrosheet")}
        )
        raise ValueError(f"unknown retrosheet dataset {name!r}; known: {known}")

    # ------------------------------------------------------------------ data quality
    def _parent(self, ref: str, year: int) -> pa.Table | None:
        """The parent table of a relationship (``<source>.<dataset>``); ``None`` if not stored or empty."""
        source, _, dataset = ref.partition(".")
        spec = get_dataset(source, dataset)
        if source == "retrosheet":
            path = self.store.part_path(spec, f"rosters_{year}", year)
            return pq.read_table(path, columns=["player_id"]) if path.exists() else None
        if not self._register_loaded:
            self._register_loaded = True
            parts = self.store.files(spec)
            if parts:
                self._register_ids = pa.concat_tables(
                    [pq.read_table(p, columns=["key_retro"]) for p in parts]
                )
        return self._register_ids

    def _quality(self, year: int, units: Sequence[str]) -> None:
        """Check the stored chunks of ``units``; findings go to the manifest and are logged."""
        with default_audit_logger.track(
            operation="retrosheet_quality_check",
            source="retrosheet",
            endpoint=f"quality:{year}",
            destination=str(self.cache_config.processed_root / "retrosheet"),
        ):
            self._quality_check(year, units)

    def _quality_check(self, year: int, units: Sequence[str]) -> None:
        for unit in units:
            for dataset, chunk in UNITS[unit][1]:
                spec, chunk_id = _spec(dataset), chunk.format(y=year)
                path = self.store.part_path(spec, chunk_id, year)
                if not path.exists():
                    continue
                table = pq.read_table(path, columns=columns_needed(dataset, spec.keys))
                findings = quality_report(
                    dataset, table, spec.keys, lambda ref: self._parent(ref, year)
                )
                manifest = self.cache_config.dataset_manifest("retrosheet", dataset, "processed")
                key = manifest_key(chunk_id, year)
                entry = manifest.get_chunk(key)
                if entry is None or dict(entry.get("quality") or {}) == findings:
                    continue
                updated = {k: v for k, v in entry.items() if k != "quality"}
                if findings:
                    updated["quality"] = findings
                manifest.put_entry(key, updated)
                for finding, count in findings.items():
                    logger.warning(
                        "retrosheet data quality: %s %s=%s (season %s)",
                        dataset,
                        finding,
                        count,
                        year,
                    )

    # ------------------------------------------------------------------ ingest everything
    def ingest_season(
        self, year: int, datasets: tuple[str, ...] | None = None, refresh: bool = False
    ) -> SeasonReport:
        """Download and parse the datasets the tree offers for one season (resumable).

        ``datasets`` are ingest units or any registry dataset name of a season unit (for example
        ``box_games`` selects ``box_accounts``); the default is every unit. Only the raw files the
        selected units read are downloaded.
        """
        units = units_for(datasets) if datasets else SEASON_DATASETS
        if bad := [u for u in units if u not in UNITS]:
            raise ValueError(f"unknown season datasets {bad}; valid: {sorted(DATASET_UNIT)}")
        with default_audit_logger.track(
            operation="retrosheet_ingest_season",
            source="retrosheet",
            endpoint=f"season:{year}",
            destination=str(self.cache_config.processed_root / "retrosheet"),
        ) as tracker:
            report = self._ingest_season(year, units, datasets, refresh)
            tracker.set_records(sum(n or 0 for n in report.datasets.values()))
            tracker.set_cache_hit(all(n is None for n in report.datasets.values()))
            return report

    def _ingest_season(
        self, year: int, units: Sequence[str], datasets: tuple[str, ...] | None, refresh: bool
    ) -> SeasonReport:
        report = SeasonReport(year=year)
        if datasets:
            kinds = tuple(dict.fromkeys(k for u in units for k in UNITS[u][0]))
            self._download(year, kinds, refresh)
            wanted = self.downloader.tree().season_files(year, kinds)
            report.complete_download = all(self.downloader.raw_path(f).exists() for f in wanted)
        else:
            download = self.downloader.download_season(year, refresh=refresh)
            if refresh:
                self._refreshed.update(
                    (year, f.kind) for f in self.downloader.tree().season_files(year)
                )
            report.complete_download = download.complete
        for unit in units:
            report.datasets.update(self._unit_write(unit, year, refresh))
        self._quality(year, units)
        return report

    def ingest_reference(self, refresh: bool = False) -> dict[str, int | None]:
        """Ingest every ``reference/*.csv`` table and every postseason/all-star game log.

        The repository's README and any file no dataset covers are kept raw as well.
        """
        with default_audit_logger.track(
            operation="retrosheet_ingest_reference",
            source="retrosheet",
            endpoint="reference",
            destination=str(self.cache_config.processed_root / "retrosheet"),
        ) as tracker:
            done = self._ingest_reference(refresh)
            tracker.set_records(sum(n or 0 for n in done.values()))
            tracker.set_cache_hit(all(n is None for n in done.values()))
            return done

    def _ingest_reference(self, refresh: bool) -> dict[str, int | None]:
        done: dict[str, int | None] = {}
        tree = self.downloader.tree()
        self.downloader.ensure_documents(refresh=refresh)
        for file in tree.reference:
            table_name = file.name.removesuffix(".csv").lower()
            dataset = f"reference_{table_name}"
            try:
                _spec(dataset)
            except KeyError:
                logger.warning("no dataset covers reference file %s yet", file.path)
                continue
            was = self._current(dataset, "data", None, self._expected([file]))
            rows = len(self.reference(table_name, refresh))
            done[dataset] = None if was and not refresh else rows
        for kind in POSTSEASON_GAMELOG_KINDS:
            log = tree.postseason_gamelog(kind)
            if log is None:
                continue
            was = self._current("gamelogs_postseason", kind, None, self._expected([log]))
            rows = len(self.postseason_game_logs(kind, refresh))
            done[f"gamelogs_postseason:{kind}"] = None if was and not refresh else rows
        return done

    def ingest_all(
        self,
        start: int | None = None,
        end: int | None = None,
        *,
        datasets: tuple[str, ...] | None = None,
        reference: bool = True,
        refresh: bool = False,
        continue_on_error: bool = False,
    ) -> IngestReport:
        """Ingest every season in ``[start, end]`` (default: all the tree lists) plus references.

        Safe to interrupt and re-run: completed files and chunks are skipped, stale ``.part``
        files are discarded, and a season only counts as downloaded when every listed file is
        present. With ``continue_on_error`` failures are collected in the report instead of
        stopping the run.
        """
        report = IngestReport()
        for year in self.downloader.seasons():
            if (start is not None and year < start) or (end is not None and year > end):
                continue
            try:
                report.seasons.append(self.ingest_season(year, datasets, refresh))
            except Exception as exc:
                if not continue_on_error:
                    raise
                logger.exception("retrosheet season %s failed", year)
                report.failures[year] = f"{type(exc).__name__}: {exc}"
        if reference:
            report.reference = self.ingest_reference(refresh)
        return report

    def local_event_files(self, year: int) -> list[Path]:
        """Downloaded play-by-play event files of a season (regular, postseason, deduced)."""
        return self.downloader.local_paths(
            year, "event_regular", "event_postseason", "event_deduced"
        )


# Module-level convenience functions
get_default_source = lazy_singleton(RetrosheetSource)


def table(
    name: str, season: int | None = None, *, kind: str | None = None, refresh: bool = False
) -> pa.Table:
    """Any Retrosheet dataset by registry name, for example ``table("box_games", 2023)``."""
    return get_default_source().table(name, season, kind=kind, refresh=refresh)


def events(year: int, include_postseason: bool = False, refresh: bool = False) -> pa.Table:
    """Extract Retrosheet play-by-play events for a season."""
    return get_default_source().events(
        year=year, include_postseason=include_postseason, refresh=refresh
    )


def events_postseason(year: int, refresh: bool = False) -> pa.Table:
    """Extract Retrosheet postseason/all-star play-by-play events for a season."""
    return get_default_source().events_postseason(year=year, refresh=refresh)


def events_deduced(year: int, refresh: bool = False) -> pa.Table:
    """Extract Retrosheet events deduced from box scores for a season."""
    return get_default_source().events_deduced(year=year, refresh=refresh)


def boxscores(year: int, refresh: bool = False) -> tuple[pa.Table, pa.Table]:
    """Extract Retrosheet batting and pitching boxscores for a season."""
    return get_default_source().boxscores(year=year, refresh=refresh)


def box_accounts(year: int, refresh: bool = False) -> dict[str, pa.Table]:
    """Extract Retrosheet box-score game accounts (``box_games``, ``box_starters``, ...) for a season."""
    return get_default_source().box_accounts(year=year, refresh=refresh)


def daily_splits(year: int, refresh: bool = False) -> pa.Table:
    """Extract Retrosheet daily player lines for a season."""
    return get_default_source().daily_splits(year=year, refresh=refresh)


def substitutions(year: int, refresh: bool = False) -> pa.Table:
    """Extract Retrosheet player substitutions for a season."""
    return get_default_source().substitutions(year=year, refresh=refresh)


def game_logs(year: int, refresh: bool = False) -> pa.Table:
    """Extract Retrosheet game logs for a season."""
    return get_default_source().game_logs(year=year, refresh=refresh)


def postseason_game_logs(kind: str, refresh: bool = False) -> pa.Table:
    """Extract Retrosheet postseason game logs (wild_card, division_series, lcs, world_series, all_star)."""
    return get_default_source().postseason_game_logs(kind=kind, refresh=refresh)


def rosters(year: int, refresh: bool = False) -> pa.Table:
    """Extract Retrosheet team rosters for a season."""
    return get_default_source().rosters(year=year, refresh=refresh)


def schedule(year: int, refresh: bool = False) -> pa.Table:
    """Extract the Retrosheet schedule of a season."""
    return get_default_source().schedule(year=year, refresh=refresh)


def schedule_original(year: int, refresh: bool = False) -> pa.Table:
    """Extract the original (pre-disruption) Retrosheet schedule of a season."""
    return get_default_source().schedule_original(year=year, refresh=refresh)


def umpires(year: int, refresh: bool = False) -> pa.Table:
    """Extract the Retrosheet umpire list of a season."""
    return get_default_source().umpires(year=year, refresh=refresh)


def discrepancies(year: int, refresh: bool = False) -> pa.Table:
    """Extract the Retrosheet data-discrepancy records of a season."""
    return get_default_source().discrepancies(year=year, refresh=refresh)


def reference(table_name: str, refresh: bool = False) -> pa.Table:
    """Extract Retrosheet reference tables (ballparks, teams, ejections, coaches, relatives, biofile)."""
    return get_default_source().reference(table_name=table_name, refresh=refresh)


def ingest_all(
    start: int | None = None,
    end: int | None = None,
    *,
    datasets: tuple[str, ...] | None = None,
    reference: bool = True,
    refresh: bool = False,
    continue_on_error: bool = False,
) -> IngestReport:
    """Ingest every Retrosheet season (and reference table) the pinned tree offers."""
    return get_default_source().ingest_all(
        start,
        end,
        datasets=datasets,
        reference=reference,
        refresh=refresh,
        continue_on_error=continue_on_error,
    )
