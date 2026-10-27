"""High-level Retrosheet extraction and query interface."""

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import ManifestTracker, atomic_write_parquet
from baseballpy.core.config import CacheConfig
from baseballpy.core.lazy import lazy_singleton
from baseballpy.sources.retrosheet.downloader import RetrosheetDownloader
from baseballpy.sources.retrosheet.parser import (
    RetrosheetBoxScoreParser,
    RetrosheetDailySplitsParser,
    RetrosheetEventParser,
    RetrosheetGameLogParser,
    RetrosheetReferenceParser,
    RetrosheetRosterParser,
    RetrosheetSubstitutionsParser,
)


class RetrosheetSource:
    """Retrosheet dataset orchestrator with two-tier raw/processed caching and pause/resume."""

    def __init__(self, cache_config: CacheConfig | None = None) -> None:
        self.cache_config = cache_config or CacheConfig()
        self.downloader = RetrosheetDownloader(cache_config=self.cache_config)
        self.processed_dir = self.cache_config.retrosheet_dir / "processed"
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = ManifestTracker(self.processed_dir / "manifest.json")

    def events(
        self, year: int, include_postseason: bool = False, refresh: bool = False
    ) -> pa.Table:
        """Extract and parse play-by-play events for a season into strongly-typed Arrow."""
        chunk_id = f"events_{year}" if not include_postseason else f"events_{year}_postseason"
        out_dir = self.processed_dir / "events" / f"season={year}"
        out_file = out_dir / ("events.parquet" if not include_postseason else "events_all.parquet")

        if not refresh and out_file.exists() and self.manifest.is_completed(chunk_id):
            return pq.read_table(out_file)

        event_files = self.downloader.download_season(
            year, include_postseason=include_postseason, refresh=refresh
        )
        parser = RetrosheetEventParser()
        table = parser.parse_files(event_files, year=year)

        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, out_file)
            self.manifest.set_completed(chunk_id, records_count=len(table))

        return table

    def boxscores(self, year: int, refresh: bool = False) -> tuple[pa.Table, pa.Table]:
        """Extract and parse batting and pitching boxscores for a season."""
        batting_chunk_id = f"box_batting_{year}"
        pitching_chunk_id = f"box_pitching_{year}"

        batting_file = (
            self.processed_dir / "boxscores_batting" / f"season={year}" / "batting.parquet"
        )
        pitching_file = (
            self.processed_dir / "boxscores_pitching" / f"season={year}" / "pitching.parquet"
        )

        if (
            not refresh
            and batting_file.exists()
            and pitching_file.exists()
            and self.manifest.is_completed(batting_chunk_id)
            and self.manifest.is_completed(pitching_chunk_id)
        ):
            return pq.read_table(batting_file), pq.read_table(pitching_file)

        event_files = self.downloader.download_season(year, refresh=refresh)
        parser = RetrosheetBoxScoreParser()
        batting_table, pitching_table = parser.parse_files(event_files, year=year)

        if self.cache_config.enabled:
            if len(batting_table) > 0:
                atomic_write_parquet(batting_table, batting_file)
                self.manifest.set_completed(batting_chunk_id, records_count=len(batting_table))
            if len(pitching_table) > 0:
                atomic_write_parquet(pitching_table, pitching_file)
                self.manifest.set_completed(pitching_chunk_id, records_count=len(pitching_table))

        return batting_table, pitching_table

    def daily_splits(self, year: int, refresh: bool = False) -> pa.Table:
        """Extract and parse daily player lines for a season."""
        chunk_id = f"daily_splits_{year}"
        out_dir = self.processed_dir / "daily_splits" / f"season={year}"
        out_file = out_dir / "daily_splits.parquet"

        if not refresh and out_file.exists() and self.manifest.is_completed(chunk_id):
            return pq.read_table(out_file)

        event_files = self.downloader.download_season(year, refresh=refresh)
        parser = RetrosheetDailySplitsParser()
        table = parser.parse_files(event_files, year=year)

        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, out_file)
            self.manifest.set_completed(chunk_id, records_count=len(table))

        return table

    def substitutions(self, year: int, refresh: bool = False) -> pa.Table:
        """Extract and parse in-game substitutions for a season."""
        chunk_id = f"substitutions_{year}"
        out_dir = self.processed_dir / "substitutions" / f"season={year}"
        out_file = out_dir / "substitutions.parquet"

        if not refresh and out_file.exists() and self.manifest.is_completed(chunk_id):
            return pq.read_table(out_file)

        event_files = self.downloader.download_season(year, refresh=refresh)
        parser = RetrosheetSubstitutionsParser()
        table = parser.parse_files(event_files, year=year)

        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, out_file)
            self.manifest.set_completed(chunk_id, records_count=len(table))

        return table

    def game_logs(self, year: int, refresh: bool = False) -> pa.Table:
        """Extract and parse 161-column historical game logs for a season."""
        chunk_id = f"gamelogs_{year}"
        out_dir = self.processed_dir / "gamelogs"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"gl{year}.parquet"

        if not refresh and out_file.exists() and self.manifest.is_completed(chunk_id):
            return pq.read_table(out_file)

        raw_path = self.downloader.download_gamelog(year, refresh=refresh)
        parser = RetrosheetGameLogParser()
        table = parser.parse_file(raw_path)

        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, out_file)
            self.manifest.set_completed(chunk_id, records_count=len(table))

        return table

    def postseason_game_logs(self, kind: str, refresh: bool = False) -> pa.Table:
        """Extract and parse postseason game logs (wild_card, division_series, lcs, world_series, all_star)."""
        chunk_id = f"gamelogs_postseason_{kind.lower()}"
        out_dir = self.processed_dir / "gamelogs" / "postseason"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"gl_{kind.lower()}.parquet"

        if not refresh and out_file.exists() and self.manifest.is_completed(chunk_id):
            return pq.read_table(out_file)

        raw_path = self.downloader.download_postseason_gamelog(kind, refresh=refresh)
        parser = RetrosheetGameLogParser()
        table = parser.parse_file(raw_path)

        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, out_file)
            self.manifest.set_completed(chunk_id, records_count=len(table))

        return table

    def rosters(self, year: int, refresh: bool = False) -> pa.Table:
        """Extract and parse team rosters for a season."""
        chunk_id = f"rosters_{year}"
        out_dir = self.processed_dir / "rosters"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"rosters_{year}.parquet"

        if not refresh and out_file.exists() and self.manifest.is_completed(chunk_id):
            return pq.read_table(out_file)

        self.downloader.download_season(year, refresh=refresh)
        season_dir = self.downloader.raw_dir / str(year)
        roster_files = list(season_dir.glob("*.ROS"))

        parser = RetrosheetRosterParser()
        table = parser.parse_files(roster_files, year=year)

        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, out_file)
            self.manifest.set_completed(chunk_id, records_count=len(table))

        return table

    def reference(self, table_name: str, refresh: bool = False) -> pa.Table:
        """Extract and parse reference tables (ballparks, teams, ejections, coaches, relatives, biofile)."""
        chunk_id = f"reference_{table_name.lower()}"
        out_dir = self.processed_dir / "reference"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{table_name.lower()}.parquet"

        if not refresh and out_file.exists() and self.manifest.is_completed(chunk_id):
            return pq.read_table(out_file)

        raw_path = self.downloader.download_reference_table(table_name, refresh=refresh)
        parser = RetrosheetReferenceParser()
        table = parser.parse_file(table_name, raw_path)

        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, out_file)
            self.manifest.set_completed(chunk_id, records_count=len(table))

        return table


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
