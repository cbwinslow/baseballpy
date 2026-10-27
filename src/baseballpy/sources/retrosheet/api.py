"""High-level Retrosheet extraction and query interface (lake layout v2)."""

from collections.abc import Callable
from pathlib import Path

import pyarrow as pa

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec, get_dataset
from baseballpy.core.lazy import lazy_singleton
from baseballpy.core.stores import ProcessedStore
from baseballpy.sources import catalog
from baseballpy.sources.retrosheet.downloader import POSTSEASON_SUFFIXES, RetrosheetDownloader
from baseballpy.sources.retrosheet.parser import (
    RetrosheetBoxScoreParser,
    RetrosheetDailySplitsParser,
    RetrosheetEventParser,
    RetrosheetGameLogParser,
    RetrosheetReferenceParser,
    RetrosheetRosterParser,
    RetrosheetSubstitutionsParser,
)


def _spec(name: str) -> DatasetSpec:
    return get_dataset("retrosheet", name)


class RetrosheetSource:
    """Retrosheet dataset orchestrator: raw/ bytes, processed/ Parquet, pause/resume."""

    def __init__(self, cache_config: LakeConfig | None = None) -> None:
        catalog.register_all()
        self.cache_config = cache_config or LakeConfig()
        self.downloader = RetrosheetDownloader(cache_config=self.cache_config)
        self.store = ProcessedStore(self.cache_config)

    def _cached(
        self,
        name: str,
        chunk_id: str,
        season: int | None,
        refresh: bool,
        build: Callable[[], pa.Table],
    ) -> pa.Table:
        """Return the stored part if complete, else build, store (if non-empty) and return it."""
        spec = _spec(name)
        if not refresh and self.store.is_cached(spec, chunk_id, season):
            return self.store.read_part(spec, chunk_id, season)
        table = build()
        if self.cache_config.enabled and len(table) > 0:
            self.store.put(spec, table, chunk_id=chunk_id, season=season)
        return table

    def events(
        self, year: int, include_postseason: bool = False, refresh: bool = False
    ) -> pa.Table:
        """Parse play-by-play events for a season into strongly-typed Arrow.

        Regular-season and postseason events are separate datasets (``events`` and
        ``events_postseason``); ``include_postseason=True`` returns both concatenated.
        """
        regular = self._cached(
            "events",
            "events",
            year,
            refresh,
            lambda: RetrosheetEventParser().parse_files(
                self.downloader.download_season(year, refresh=refresh), year=year
            ),
        )
        if not include_postseason:
            return regular

        def build_postseason() -> pa.Table:
            files = self.downloader.download_season(year, include_postseason=True, refresh=refresh)
            post = [p for p in files if p.name.endswith(POSTSEASON_SUFFIXES)]
            return RetrosheetEventParser().parse_files(post, year=year)

        postseason = self._cached("events_postseason", "events", year, refresh, build_postseason)
        if len(postseason) == 0:
            return regular
        return pa.concat_tables([regular, postseason], promote_options="permissive")

    def boxscores(self, year: int, refresh: bool = False) -> tuple[pa.Table, pa.Table]:
        """Parse batting and pitching boxscores for a season."""
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
        files = self.downloader.download_season(year, refresh=refresh)
        batting, pitching = RetrosheetBoxScoreParser().parse_files(files, year=year)
        if self.cache_config.enabled:
            if len(batting) > 0:
                self.store.put(spec_b, batting, chunk_id="batting", season=year)
            if len(pitching) > 0:
                self.store.put(spec_p, pitching, chunk_id="pitching", season=year)
        return batting, pitching

    def daily_splits(self, year: int, refresh: bool = False) -> pa.Table:
        """Parse daily player lines for a season."""
        return self._cached(
            "daily_splits",
            "daily_splits",
            year,
            refresh,
            lambda: RetrosheetDailySplitsParser().parse_files(
                self.downloader.download_season(year, refresh=refresh), year=year
            ),
        )

    def substitutions(self, year: int, refresh: bool = False) -> pa.Table:
        """Parse in-game substitutions for a season."""
        return self._cached(
            "substitutions",
            "substitutions",
            year,
            refresh,
            lambda: RetrosheetSubstitutionsParser().parse_files(
                self.downloader.download_season(year, refresh=refresh), year=year
            ),
        )

    def game_logs(self, year: int, refresh: bool = False) -> pa.Table:
        """Parse 161-column historical game logs for a season."""
        return self._cached(
            "gamelogs",
            f"gl{year}",
            year,
            refresh,
            lambda: RetrosheetGameLogParser().parse_file(
                self.downloader.download_gamelog(year, refresh=refresh)
            ),
        )

    def postseason_game_logs(self, kind: str, refresh: bool = False) -> pa.Table:
        """Parse postseason game logs (wild_card, division_series, lcs, world_series, all_star)."""
        return self._cached(
            "gamelogs_postseason",
            kind.lower(),
            None,
            refresh,
            lambda: RetrosheetGameLogParser().parse_file(
                self.downloader.download_postseason_gamelog(kind, refresh=refresh)
            ),
        )

    def rosters(self, year: int, refresh: bool = False) -> pa.Table:
        """Parse team rosters for a season."""

        def build() -> pa.Table:
            self.downloader.download_season(year, refresh=refresh)
            roster_files: list[Path] = sorted(self.downloader.roster_dir(year).glob("*.ROS"))
            return RetrosheetRosterParser().parse_files(roster_files, year=year)

        return self._cached("rosters", f"rosters_{year}", year, refresh, build)

    def reference(self, table_name: str, refresh: bool = False) -> pa.Table:
        """Parse reference tables (ballparks, teams, ejections, coaches, relatives, biofile)."""
        return self._cached(
            f"reference_{table_name.lower()}",
            "data",
            None,
            refresh,
            lambda: RetrosheetReferenceParser().parse_file(
                table_name, self.downloader.download_reference_table(table_name, refresh=refresh)
            ),
        )


# Module-level convenience functions
get_default_source = lazy_singleton(RetrosheetSource)


def events(year: int, include_postseason: bool = False, refresh: bool = False) -> pa.Table:
    """Extract Retrosheet play-by-play events for a season."""
    return get_default_source().events(
        year=year, include_postseason=include_postseason, refresh=refresh
    )


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


def reference(table_name: str, refresh: bool = False) -> pa.Table:
    """Extract Retrosheet reference tables (ballparks, teams, ejections, coaches, relatives, biofile)."""
    return get_default_source().reference(table_name=table_name, refresh=refresh)
