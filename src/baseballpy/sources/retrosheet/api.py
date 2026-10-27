"""High-level Retrosheet extraction, parsing and ingest interface (lake layout v2).

Parsing streams: each upstream file is parsed to one Arrow table (optionally in a bounded process
pool) and the tables are written as row groups of one atomic Parquet part per dataset and season.
Every dataset the pinned tree offers can be ingested with :meth:`RetrosheetSource.ingest_all`,
which resumes after interruption because completed chunks are recorded in manifests.
"""

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec, get_dataset
from baseballpy.core.lazy import lazy_singleton
from baseballpy.core.stores import ProcessedStore
from baseballpy.sources import catalog
from baseballpy.sources.retrosheet.downloader import RetrosheetDownloader
from baseballpy.sources.retrosheet.pool import parse_stream
from baseballpy.sources.retrosheet.tree import POSTSEASON_GAMELOG_KINDS

logger = logging.getLogger(__name__)

#: season-partitioned datasets in the order :meth:`RetrosheetSource.ingest_season` writes them
SEASON_DATASETS = (
    "events",
    "events_postseason",
    "events_deduced",
    "boxscores",  # writes boxscores_batting and boxscores_pitching
    "daily_splits",
    "substitutions",
    "rosters",
    "gamelogs",
    "schedule",
    "schedule_original",
    "umpires",
    "discrepancies",
)

_EVENT_KIND = {
    "events": "event_regular",
    "events_postseason": "event_postseason",
    "events_deduced": "event_deduced",
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

    # ------------------------------------------------------------------ plumbing
    @property
    def _workers(self) -> int:
        return self.cache_config.parse_workers

    @property
    def _ref(self) -> str:
        return self.downloader.source_ref.ref

    def _write(
        self,
        name: str,
        chunk_id: str,
        season: int | None,
        refresh: bool,
        batches: Callable[[], Iterator[pa.Table]],
    ) -> int | None:
        """Stream ``batches()`` into the dataset chunk unless it is already complete.

        Returns the rows written, or ``None`` when the chunk was already cached.
        """
        spec = _spec(name)
        if not refresh and self.store.is_cached(spec, chunk_id, season):
            return None
        if not self.cache_config.enabled:
            return int(sum(t.num_rows for t in batches()))
        rows: int = self.store.put_stream(
            spec, batches(), chunk_id=chunk_id, season=season, source_ref=self._ref
        )
        return rows

    def _read(
        self,
        name: str,
        chunk_id: str,
        season: int | None,
        refresh: bool,
        batches: Callable[[], Iterator[pa.Table]],
    ) -> pa.Table:
        """``_write`` then return the stored table (or the parsed one when caching is off)."""
        if not self.cache_config.enabled:
            tables = list(batches())
            return pa.concat_tables(tables) if tables else _spec(name).schema.empty_table()
        self._write(name, chunk_id, season, refresh, batches)
        return self.store.read_part(_spec(name), chunk_id, season)

    # ------------------------------------------------------------------ event-file datasets
    def _event_batches(
        self, name: str, year: int, refresh: bool, kind: str = "events"
    ) -> Callable[[], Iterator[pa.Table]]:
        file_kind = _EVENT_KIND[name]

        def make() -> Iterator[pa.Table]:
            self.downloader.download_season(year, kinds=("team", file_kind), refresh=refresh)
            paths = self.downloader.local_paths(year, file_kind)
            yield from _tables(parse_stream(kind, paths, year, self._workers))

        return make

    def events(
        self, year: int, include_postseason: bool = False, refresh: bool = False
    ) -> pa.Table:
        """Typed play-by-play events of the regular season (``.EVA``/``.EVN`` files).

        ``include_postseason=True`` also returns the postseason/all-star events (a separate
        dataset, ``events_postseason``) concatenated after the regular-season rows.
        """
        regular = self._read(
            "events", "events", year, refresh, self._event_batches("events", year, refresh)
        )
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
        return self._read(
            "events_postseason",
            "events",
            year,
            refresh,
            self._event_batches("events_postseason", year, refresh),
        )

    def events_deduced(self, year: int, refresh: bool = False) -> pa.Table:
        """Typed events deduced from box scores (``.EDA/.EDN/.EDF`` files)."""
        return self._read(
            "events_deduced",
            "events",
            year,
            refresh,
            self._event_batches("events_deduced", year, refresh),
        )

    def _derived(self, kind: str, name: str, chunk_id: str, year: int, refresh: bool) -> pa.Table:
        def make() -> Iterator[pa.Table]:
            self.downloader.download_season(year, kinds=("team", "event_regular"), refresh=refresh)
            paths = self.downloader.local_paths(year, "event_regular")
            yield from _tables(parse_stream(kind, paths, year, self._workers))

        return self._read(name, chunk_id, year, refresh, make)

    def boxscores(self, year: int, refresh: bool = False) -> tuple[pa.Table, pa.Table]:
        """Batting and pitching boxscores derived from the regular-season event files."""
        spec_b, spec_p = _spec("boxscores_batting"), _spec("boxscores_pitching")
        if (
            not refresh
            and self.store.is_cached(spec_b, "batting", year)
            and self.store.is_cached(spec_p, "pitching", year)
        ):
            return (
                self.store.read_part(spec_b, "batting", year),
                self.store.read_part(spec_p, "pitching", year),
            )
        self.downloader.download_season(year, kinds=("team", "event_regular"), refresh=refresh)
        paths = self.downloader.local_paths(year, "event_regular")
        batting: list[pa.Table] = []
        pitching: list[pa.Table] = []
        for pair in parse_stream("boxscores", paths, year, self._workers):
            bat, pit = _pair(pair)
            batting.append(bat)
            pitching.append(pit)
        if self.cache_config.enabled:
            self.store.put_stream(
                spec_b, iter(batting), chunk_id="batting", season=year, source_ref=self._ref
            )
            self.store.put_stream(
                spec_p, iter(pitching), chunk_id="pitching", season=year, source_ref=self._ref
            )
            return (
                self.store.read_part(spec_b, "batting", year),
                self.store.read_part(spec_p, "pitching", year),
            )
        return (
            pa.concat_tables(batting) if batting else spec_b.schema.empty_table(),
            pa.concat_tables(pitching) if pitching else spec_p.schema.empty_table(),
        )

    def daily_splits(self, year: int, refresh: bool = False) -> pa.Table:
        """Daily player appearance lines derived from the regular-season event files."""
        return self._derived("daily_splits", "daily_splits", "daily_splits", year, refresh)

    def substitutions(self, year: int, refresh: bool = False) -> pa.Table:
        """In-game substitutions derived from the regular-season event files."""
        return self._derived("substitutions", "substitutions", "substitutions", year, refresh)

    # ------------------------------------------------------------------ other season files
    def _files(
        self, kind: str, parse: str, name: str, chunk_id: str, year: int, refresh: bool
    ) -> pa.Table:
        def make() -> Iterator[pa.Table]:
            self.downloader.download_season(year, kinds=(kind,), refresh=refresh)
            paths = self.downloader.local_paths(year, kind)
            yield from _tables(parse_stream(parse, paths, year, self._workers))

        return self._read(name, chunk_id, year, refresh, make)

    def rosters(self, year: int, refresh: bool = False) -> pa.Table:
        """Team rosters (``*.ROS``) for a season."""
        return self._files("roster", "rosters", "rosters", f"rosters_{year}", year, refresh)

    def schedule(self, year: int, refresh: bool = False) -> pa.Table:
        """The season schedule (``<year>schedule.csv``), including future seasons when listed."""
        return self._files(
            "schedule", "flat:schedule", "schedule", f"schedule_{year}", year, refresh
        )

    def schedule_original(self, year: int, refresh: bool = False) -> pa.Table:
        """The original (pre-disruption) schedule, e.g. 2020's ``2020sched-orig.csv``."""
        return self._files(
            "schedule_original",
            "flat:schedule_original",
            "schedule_original",
            f"schedule_original_{year}",
            year,
            refresh,
        )

    def umpires(self, year: int, refresh: bool = False) -> pa.Table:
        """Umpires of a season (``UMPIRES<year>.txt``)."""
        return self._files("umpires", "flat:umpires", "umpires", f"umpires_{year}", year, refresh)

    def discrepancies(self, year: int, refresh: bool = False) -> pa.Table:
        """Known data discrepancies of a season (AL/NL/federal ``*discs.csv`` files)."""
        return self._files(
            "discrepancies",
            "flat:discrepancies",
            "discrepancies",
            f"discrepancies_{year}",
            year,
            refresh,
        )

    def game_logs(self, year: int, refresh: bool = False) -> pa.Table:
        """The season's 161-column game log (``GL<year>.TXT``)."""

        def make() -> Iterator[pa.Table]:
            path = self.downloader.download_gamelog(year, refresh=refresh)
            yield from _tables(parse_stream("gamelogs", [path], year, self._workers))

        return self._read("gamelogs", f"gl{year}", year, refresh, make)

    def postseason_game_logs(self, kind: str, refresh: bool = False) -> pa.Table:
        """Postseason/all-star game logs (wild_card, division_series, lcs, world_series, all_star)."""

        def make() -> Iterator[pa.Table]:
            path = self.downloader.download_postseason_gamelog(kind, refresh=refresh)
            yield from _tables(parse_stream("gamelogs", [path], None, self._workers))

        return self._read("gamelogs_postseason", kind.lower(), None, refresh, make)

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

        return self._read(dataset, "data", None, refresh, make)

    # ------------------------------------------------------------------ ingest everything
    def ingest_season(
        self, year: int, datasets: tuple[str, ...] | None = None, refresh: bool = False
    ) -> SeasonReport:
        """Download and parse every dataset the tree offers for one season (resumable)."""
        wanted = datasets or SEASON_DATASETS
        unknown = set(wanted) - set(SEASON_DATASETS)
        if unknown:
            raise ValueError(f"unknown season datasets {sorted(unknown)}; valid: {SEASON_DATASETS}")
        report = SeasonReport(year=year)
        download = self.downloader.download_season(year, refresh=refresh)
        report.complete_download = download.complete
        for name in wanted:
            if name == "boxscores":
                cached = all(
                    self.store.is_cached(_spec(n), c, year)
                    for n, c in (
                        ("boxscores_batting", "batting"),
                        ("boxscores_pitching", "pitching"),
                    )
                )
                bat, pit = self.boxscores(year, refresh)
                report.datasets["boxscores_batting"] = None if cached and not refresh else len(bat)
                report.datasets["boxscores_pitching"] = None if cached and not refresh else len(pit)
                continue
            chunk = {
                "events": "events",
                "events_postseason": "events",
                "events_deduced": "events",
                "daily_splits": "daily_splits",
                "substitutions": "substitutions",
                "rosters": f"rosters_{year}",
                "gamelogs": f"gl{year}",
                "schedule": f"schedule_{year}",
                "schedule_original": f"schedule_original_{year}",
                "umpires": f"umpires_{year}",
                "discrepancies": f"discrepancies_{year}",
            }[name]
            before = self.store.is_cached(_spec(name), chunk, year)
            if name == "gamelogs" and not self.downloader.tree().season_files(year, ["gamelog"]):
                # the tree lists no game log for this season (e.g. a future schedule-only year)
                if not before or refresh:
                    self.store.put_stream(
                        _spec(name), iter(()), chunk_id=chunk, season=year, source_ref=self._ref
                    )
                report.datasets[name] = None if before and not refresh else 0
                continue
            table = getattr(self, name if name != "gamelogs" else "game_logs")(year, refresh)
            report.datasets[name] = None if before and not refresh else len(table)
        return report

    def ingest_reference(self, refresh: bool = False) -> dict[str, int | None]:
        """Ingest every ``reference/*.csv`` table and every postseason/all-star game log."""
        done: dict[str, int | None] = {}
        tree = self.downloader.tree()
        for file in tree.reference:
            table_name = file.name.removesuffix(".csv").lower()
            dataset = f"reference_{table_name}"
            try:
                spec = _spec(dataset)
            except KeyError:
                logger.warning("no dataset covers reference file %s yet", file.path)
                continue
            was = self.store.is_cached(spec, "data", None)
            rows = len(self.reference(table_name, refresh))
            done[dataset] = None if was and not refresh else rows
        for kind in POSTSEASON_GAMELOG_KINDS:
            if tree.postseason_gamelog(kind) is None:
                continue
            spec = _spec("gamelogs_postseason")
            was = self.store.is_cached(spec, kind, None)
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
