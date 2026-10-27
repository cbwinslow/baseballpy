"""Public interface for MLB Stats API data extraction and live streaming."""

from collections.abc import AsyncIterator
from typing import Any

import pyarrow as pa

from baseballpy.core.config import CacheConfig
from baseballpy.core.lazy import lazy_singleton
from baseballpy.sources.mlb_api.extractor import MlbApiExtractor
from baseballpy.sources.mlb_api.stream import GamedayLiveStreamer


class MlbApiSource:
    """Orchestrator for MLB Stats API historical and live data extraction."""

    def __init__(self, cache_config: CacheConfig | None = None) -> None:
        self.cache_config = cache_config or CacheConfig()
        self.extractor = MlbApiExtractor(cache_config=self.cache_config)

    def schedule(
        self,
        season: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        refresh: bool = False,
    ) -> pa.Table:
        """Extract and normalize schedule."""
        return self.extractor.extract_schedule(
            season=season, start_date=start_date, end_date=end_date, refresh=refresh
        )

    def boxscore(self, game_pk: int, refresh: bool = False) -> tuple[pa.Table, pa.Table]:
        """Extract game boxscore as (batting_table, pitching_table)."""
        return self.extractor.extract_boxscore(game_pk=game_pk, refresh=refresh)

    def standings(self, season: int = 2024, refresh: bool = False) -> pa.Table:
        """Extract league standings."""
        return self.extractor.extract_standings(season=season, refresh=refresh)

    def teams(self, refresh: bool = False) -> pa.Table:
        """Extract active teams."""
        return self.extractor.extract_teams(refresh=refresh)

    def roster(self, team_id: int, refresh: bool = False) -> pa.Table:
        """Extract team roster."""
        return self.extractor.extract_roster(team_id=team_id, refresh=refresh)

    def transactions(self, season: int = 2024, refresh: bool = False) -> pa.Table:
        """Extract season transactions."""
        return self.extractor.extract_transactions(season=season, refresh=refresh)

    def draft(self, year: int = 2024, refresh: bool = False) -> pa.Table:
        """Extract draft picks."""
        return self.extractor.extract_draft(year=year, refresh=refresh)

    def venues(self, refresh: bool = False) -> pa.Table:
        """Extract venues/ballparks."""
        return self.extractor.extract_venues(refresh=refresh)

    def stream_game(
        self, game_pk: int, poll_interval: float = 2.0
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream discrete live events for an ongoing game contest."""
        streamer = GamedayLiveStreamer(game_pk=game_pk, poll_interval=poll_interval)
        return streamer.stream_events()


# Module-level convenience functions
get_default_source = lazy_singleton(MlbApiSource)


def get_schedule(
    season: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    refresh: bool = False,
) -> pa.Table:
    """Extract game schedule."""
    return get_default_source().schedule(
        season=season, start_date=start_date, end_date=end_date, refresh=refresh
    )


def get_boxscore(game_pk: int, refresh: bool = False) -> tuple[pa.Table, pa.Table]:
    """Extract game boxscore as (batting_table, pitching_table)."""
    return get_default_source().boxscore(game_pk=game_pk, refresh=refresh)


def get_standings(season: int = 2024, refresh: bool = False) -> pa.Table:
    """Extract standings for a season."""
    return get_default_source().standings(season=season, refresh=refresh)


def get_teams(refresh: bool = False) -> pa.Table:
    """Extract active teams."""
    return get_default_source().teams(refresh=refresh)


def get_roster(team_id: int, refresh: bool = False) -> pa.Table:
    """Extract active roster for a team."""
    return get_default_source().roster(team_id=team_id, refresh=refresh)


def get_transactions(season: int = 2024, refresh: bool = False) -> pa.Table:
    """Extract transactions for a season."""
    return get_default_source().transactions(season=season, refresh=refresh)


def get_draft(year: int = 2024, refresh: bool = False) -> pa.Table:
    """Extract draft picks for a year."""
    return get_default_source().draft(year=year, refresh=refresh)


def get_venues(refresh: bool = False) -> pa.Table:
    """Extract ballparks and venues."""
    return get_default_source().venues(refresh=refresh)


def stream_game(game_pk: int, poll_interval: float = 2.0) -> AsyncIterator[dict[str, Any]]:
    """Stream discrete live play events from an active game."""
    return get_default_source().stream_game(game_pk=game_pk, poll_interval=poll_interval)
