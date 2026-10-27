"""Public interface for MLB Stats API data extraction and live streaming."""

from collections.abc import AsyncIterator
from typing import Any

import pyarrow as pa

from baseballpy.core.config import LakeConfig
from baseballpy.core.lazy import lazy_singleton
from baseballpy.sources.mlb_api.endpoints import SUPPORTED, Context
from baseballpy.sources.mlb_api.extractor import MlbApiExtractor
from baseballpy.sources.mlb_api.generic import (
    EndpointReport,
    MlbEndpointExtractor,
    read_endpoint,
)
from baseballpy.sources.mlb_api.stream import GamedayLiveStreamer


class MlbApiSource:
    """Orchestrator for MLB Stats API historical and live data extraction."""

    def __init__(self, cache_config: LakeConfig | None = None) -> None:
        self.cache_config = cache_config or LakeConfig()
        self.extractor = MlbApiExtractor(cache_config=self.cache_config)
        self.endpoints = MlbEndpointExtractor(cache_config=self.cache_config)

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

    def endpoint(
        self,
        name: str,
        season: int | None = None,
        sport_ids: tuple[int, ...] = (1,),
        game_pks: tuple[int, ...] = (),
        refresh: bool = False,
    ) -> pa.Table:
        """Ingest a declarative endpoint (see ``endpoints.ENDPOINTS``) and return its rows."""
        ctx = self._context(season, sport_ids, game_pks)
        self.endpoints.ingest(name, ctx, refresh=refresh)
        return read_endpoint(name, season, self.cache_config)

    def _context(
        self, season: int | None, sport_ids: tuple[int, ...], game_pks: tuple[int, ...] = ()
    ) -> Context:
        """Fan-out values from what is already in the lake (teams, leader categories)."""
        teams: list[int] = []
        if season is not None:
            try:
                rows = read_endpoint("teams_season", season, self.cache_config)
                teams = sorted(set(rows.column("id").to_pylist()))
            except (KeyError, FileNotFoundError, OSError):
                teams = []
        try:
            leaders = read_endpoint("ref_league_leader_types", None, self.cache_config)
            categories = [c for c in leaders.column("display_name").to_pylist() if c]
        except (KeyError, FileNotFoundError, OSError):
            categories = []
        return Context(
            season=season,
            sport_ids=sport_ids,
            team_ids=teams,
            game_pks=game_pks,
            leader_categories=categories,
        )

    def ingest_reference(self, refresh: bool = False) -> list[EndpointReport]:
        """Ingest every flat (season-independent) endpoint: reference lists, jobs, history."""
        ctx = Context()
        return [
            self.endpoints.ingest(e, ctx, refresh=refresh) for e in SUPPORTED if not e.partitioned
        ]

    def final_game_pks(self, season: int) -> tuple[int, ...]:
        """``game_pk`` of every final game of a season, from ``schedule_hydrated``."""
        table = read_endpoint("schedule_hydrated", season, self.cache_config)
        pks = {
            pk
            for pk, state in zip(
                table.column("game_pk").to_pylist(),
                table.column("status_abstract_game_state").to_pylist(),
                strict=True,
            )
            if state == "Final"
        }
        return tuple(sorted(pks))

    def ingest_season(
        self,
        season: int,
        sport_ids: tuple[int, ...] = (1,),
        include_games: bool = False,
        max_games: int | None = None,
        include_history: bool = False,
        refresh: bool = False,
    ) -> list[EndpointReport]:
        """Ingest every season-scoped endpoint (and, optionally, per-game endpoints) of a season.

        Order matters: reference lists and ``teams_season`` first (they define the fan-out for
        team-scoped endpoints and stats leaders), then everything else; per-game endpoints use the
        final games of ``schedule_hydrated`` (``max_games`` bounds the number of games). All-time stat
        types (``career*``, ``yearByYear*``) ignore the season and take minutes per request, so they
        run only with ``include_history=True``.
        """
        reports = self.ingest_reference(refresh)
        reports.append(
            self.endpoints.ingest("teams_season", self._context(season, sport_ids), refresh=refresh)
        )
        ctx = self._context(season, sport_ids)
        season_eps = [
            e
            for e in SUPPORTED
            if e.partitioned
            and e.scope != "game"
            and e.name != "teams_season"
            and (include_history or not e.heavy)
        ]
        reports.extend(
            self.endpoints.ingest(e, ctx, refresh=refresh, allow_heavy=include_history)
            for e in season_eps
        )
        if include_games:
            pks = self.final_game_pks(season)
            pks = pks[:max_games] if max_games is not None else pks
            game_ctx = self._context(season, sport_ids, pks)
            reports.extend(
                self.endpoints.ingest(e, game_ctx, refresh=refresh)
                for e in SUPPORTED
                if e.scope == "game"
            )
        return reports

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


def get_endpoint(name: str, season: int | None = None, refresh: bool = False) -> pa.Table:
    """Ingest and return any declarative MLB endpoint dataset (``endpoints.ENDPOINTS``)."""
    return get_default_source().endpoint(name, season=season, refresh=refresh)


def ingest_season(
    season: int, include_games: bool = False, max_games: int | None = None, refresh: bool = False
) -> list[EndpointReport]:
    """Ingest every MLB endpoint of a season (``include_games`` adds per-game datasets)."""
    return get_default_source().ingest_season(
        season, include_games=include_games, max_games=max_games, refresh=refresh
    )


def stream_game(game_pk: int, poll_interval: float = 2.0) -> AsyncIterator[dict[str, Any]]:
    """Stream discrete live play events from an active game."""
    return get_default_source().stream_game(game_pk=game_pk, poll_interval=poll_interval)
