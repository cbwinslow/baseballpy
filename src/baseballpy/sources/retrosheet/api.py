"""High-level Retrosheet extraction and query interface."""

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import ManifestTracker, atomic_write_parquet
from baseballpy.core.config import CacheConfig
from baseballpy.sources.retrosheet.downloader import RetrosheetDownloader
from baseballpy.sources.retrosheet.parser import (
    RetrosheetEventParser,
    RetrosheetGameLogParser,
    RetrosheetRosterParser,
)


class RetrosheetSource:
    """Retrosheet dataset orchestrator with two-tier raw/processed caching and pause/resume."""

    def __init__(self, cache_config: CacheConfig | None = None) -> None:
        self.cache_config = cache_config or CacheConfig()
        self.downloader = RetrosheetDownloader(cache_config=self.cache_config)
        self.processed_dir = self.cache_config.retrosheet_dir / "processed"
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = ManifestTracker(self.processed_dir / "manifest.json")

    def events(self, year: int, refresh: bool = False) -> pa.Table:
        """Extract and parse play-by-play events for a season into strongly-typed Arrow."""
        chunk_id = f"events_{year}"
        out_dir = self.processed_dir / "events" / f"season={year}"
        out_file = out_dir / "events.parquet"

        if not refresh and out_file.exists() and self.manifest.is_completed(chunk_id):
            return pq.read_table(out_file)

        event_files = self.downloader.download_season(year, refresh=refresh)
        parser = RetrosheetEventParser()
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

    def rosters(self, year: int, refresh: bool = False) -> pa.Table:
        """Extract and parse team rosters for a season."""
        chunk_id = f"rosters_{year}"
        out_dir = self.processed_dir / "rosters"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"rosters_{year}.parquet"

        if not refresh and out_file.exists() and self.manifest.is_completed(chunk_id):
            return pq.read_table(out_file)

        # Ensure raw season directory is populated
        self.downloader.download_season(year, refresh=refresh)
        season_dir = self.downloader.raw_dir / str(year)
        roster_files = list(season_dir.glob("*.ROS"))

        parser = RetrosheetRosterParser()
        table = parser.parse_files(roster_files, year=year)

        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, out_file)
            self.manifest.set_completed(chunk_id, records_count=len(table))

        return table


# Module-level convenience functions
_default_source = RetrosheetSource()


def events(year: int, refresh: bool = False) -> pa.Table:
    """Extract Retrosheet play-by-play events for a season."""
    return _default_source.events(year=year, refresh=refresh)


def game_logs(year: int, refresh: bool = False) -> pa.Table:
    """Extract Retrosheet game logs for a season."""
    return _default_source.game_logs(year=year, refresh=refresh)


def rosters(year: int, refresh: bool = False) -> pa.Table:
    """Extract Retrosheet team rosters for a season."""
    return _default_source.rosters(year=year, refresh=refresh)
