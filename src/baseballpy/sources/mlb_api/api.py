"""Public interface for MLB Stats API data extraction and live streaming."""

from collections.abc import AsyncIterator
from typing import Any

import pyarrow as pa

from baseballpy.core.config import LakeConfig
from baseballpy.core.lazy import lazy_singleton
from baseballpy.sources.mlb_api.endpoints import SUPPORTED, Context, MlbEndpoint
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

    def standings(self, season: int | None = None, refresh: bool = False) -> pa.Table:
        """Extract league standings."""
        return self.extractor.extract_standings(season=season, refresh=refresh)

    def teams(self, refresh: bool = False) -> pa.Table:
        """Extract active teams."""
        return self.extractor.extract_teams(refresh=refresh)

    def roster(self, team_id: int, refresh: bool = False) -> pa.Table:
        """Extract team roster."""
        return self.extractor.extract_roster(team_id=team_id, refresh=refresh)

    def transactions(self, season: int | None = None, refresh: bool = False) -> pa.Table:
        """Extract season transactions."""
        return self.extractor.extract_transactions(season=season, refresh=refresh)

    def draft(self, year: int | None = None, refresh: bool = False) -> pa.Table:
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
        person_ids: tuple[int, ...] = (),
        updated_since: str | None = None,
        query: str | None = None,
        refresh: bool = False,
    ) -> pa.Table:
        """Ingest a declarative endpoint (see ``endpoints.ENDPOINTS``) and return its rows.

        ``person_ids`` fan out per-player stats, ``updated_since`` drives the incremental
        ``people_changes``/``game_changes`` logs and ``query`` the on-demand ``people_search``.
        """
        ctx = self._context(season, sport_ids, game_pks, person_ids, updated_since, query)
        self.endpoints.ingest(name, ctx, refresh=refresh)
        return read_endpoint(name, season, self.cache_config)

    def _ids(self, endpoint: str, season: int | None, column: str) -> list[Any]:
        """Distinct values of ``column`` of an already ingested dataset (empty if not ingested)."""
        try:
            rows = read_endpoint(endpoint, season, self.cache_config)
            return sorted({v for v in rows.column(column).to_pylist() if v is not None})
        except (KeyError, FileNotFoundError, OSError):
            return []

    def _context(
        self,
        season: int | None,
        sport_ids: tuple[int, ...],
        game_pks: tuple[int, ...] = (),
        person_ids: tuple[int, ...] = (),
        updated_since: str | None = None,
        query: str | None = None,
        opposing_team_ids: tuple[int, ...] = (),
        opposing_player_ids: tuple[int, ...] = (),
    ) -> Context:
        """Fan-out values from what is already in the lake (teams, leader categories, awards)."""
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
            person_ids=person_ids,
            award_ids=[str(a) for a in self._ids("ref_awards", None, "id")],
            updated_since=updated_since,
            query=query,
            sit_codes=[str(c) for c in self._ids("ref_situation_codes", None, "code")],
            metrics=[str(m) for m in self._ids("ref_metrics", None, "name") if m],
            opposing_team_ids=opposing_team_ids,
            opposing_player_ids=opposing_player_ids,
        )

    def ingest_reference(self, refresh: bool = False) -> list[EndpointReport]:
        """Ingest every flat (season-independent) endpoint: reference lists, jobs, history."""
        ctx = Context()
        return [
            self.endpoints.ingest(e, ctx, refresh=refresh, keep_going=True)
            for e in SUPPORTED
            if e.scope == "flat"
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
        sport_ids: tuple[int, ...] | None = None,
        include_games: bool = False,
        max_games: int | None = None,
        include_history: bool = False,
        include_awards: bool = True,
        include_people_stats: bool = False,
        max_people: int | None = None,
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
        sports = sport_ids if sport_ids is not None else self.all_sport_ids()
        reports.append(
            self.endpoints.ingest(
                "teams_season", self._context(season, sports), refresh=refresh, keep_going=True
            )
        )
        ctx = self._context(season, sports)
        season_eps = [
            e
            for e in SUPPORTED
            if e.partitioned
            and e.scope != "game"
            and e.name != "teams_season"
            and e.scope not in ("person_season",)
            and (include_awards or e.scope != "award_season")
            and (include_history or not e.heavy)
        ]
        reports.extend(
            self.endpoints.ingest(
                e, ctx, refresh=refresh, allow_heavy=include_history, keep_going=True
            )
            for e in season_eps
        )
        if include_people_stats:
            reports.extend(
                self.ingest_people_stats(
                    season, max_people=max_people, sport_ids=sports, refresh=refresh
                )
            )
        if include_games:
            pks = self.final_game_pks(season)
            pks = pks[:max_games] if max_games is not None else pks
            game_ctx = self._context(season, sports, pks)
            reports.extend(
                self.endpoints.ingest(e, game_ctx, refresh=refresh, keep_going=True)
                for e in SUPPORTED
                if e.scope == "game"
            )
        return reports

    def all_sport_ids(self) -> tuple[int, ...]:
        """Every sport/level the provider lists (``ref_sports``: MLB, the minors, winter, ...)."""
        ids = self._ids("ref_sports", None, "id")
        return tuple(int(i) for i in ids) or (1,)

    def ingest_history(self, season: int, refresh: bool = False) -> list[EndpointReport]:
        """Ingest the all-time stat pools (``career*``, ``yearByYear*``, ``statsSingleSeason*``).

        These ignore the season and return every player in history, so they are stored once as a
        snapshot under ``season`` (the season of the run) instead of once per season; expect minutes
        per request and up to ~190k rows for the largest.
        """
        ctx = self._context(season, self.all_sport_ids())
        return [
            self.endpoints.ingest(e, ctx, refresh=refresh, allow_heavy=True, keep_going=True)
            for e in SUPPORTED
            if e.heavy and e.scope != "person_season"
        ]

    def ingest_people_stats(
        self,
        season: int,
        person_ids: tuple[int, ...] | None = None,
        max_people: int | None = None,
        sport_ids: tuple[int, ...] = (1,),
        families: tuple[str, ...] = (),
        opposing_team_ids: tuple[int, ...] = (),
        opposing_player_ids: tuple[int, ...] = (),
        refresh: bool = False,
    ) -> list[EndpointReport]:
        """Ingest every ``people_stats_*`` endpoint for ``person_ids`` (default: ``players_season``).

        One request per person and stat combination, so this is opt-in and ``max_people`` bounds it.
        Two families are additionally opt-in because their cross product is huge: ``"metrics"``
        (every tracking metric per person: ``metricAverages``/``metricLog``) and ``"matchups"``
        (``vsPlayer*``/``vsTeam*`` need the opposing ids passed here).
        """
        unknown = set(families) - {"metrics", "matchups"}
        if unknown:
            raise ValueError(f"unknown people-stats families {sorted(unknown)}")
        ids = (
            tuple(person_ids)
            if person_ids is not None
            else tuple(self._ids("players_season", season, "id"))
        )
        ids = ids[:max_people] if max_people is not None else ids
        ctx = self._context(
            season,
            sport_ids,
            person_ids=ids,
            opposing_team_ids=opposing_team_ids,
            opposing_player_ids=opposing_player_ids,
        )
        needed = {"opposing_team_id": opposing_team_ids, "opposing_player_id": opposing_player_ids}

        def wanted(endpoint: MlbEndpoint) -> bool:
            for dim in endpoint.fan_out:
                family = "metrics" if dim == "metric" else "matchups"
                if family not in families:
                    return False
                if dim in needed and not needed[dim]:
                    raise ValueError(
                        f"{endpoint.name} needs {dim}s: pass opposing_team_ids/opposing_player_ids"
                    )
            return True

        return [
            self.endpoints.ingest(e, ctx, refresh=refresh, keep_going=True)
            for e in SUPPORTED
            if e.scope == "person_season" and wanted(e)
        ]

    def stream_game(
        self, game_pk: int, poll_interval: float = 2.0
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream discrete live events for an ongoing game contest."""
        streamer = GamedayLiveStreamer(poll_interval=poll_interval, lake=self.cache_config)
        return streamer.stream_events(game_pk)


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


def get_standings(season: int | None = None, refresh: bool = False) -> pa.Table:
    """Extract standings for a season."""
    return get_default_source().standings(season=season, refresh=refresh)


def get_teams(refresh: bool = False) -> pa.Table:
    """Extract active teams."""
    return get_default_source().teams(refresh=refresh)


def get_roster(team_id: int, refresh: bool = False) -> pa.Table:
    """Extract active roster for a team."""
    return get_default_source().roster(team_id=team_id, refresh=refresh)


def get_transactions(season: int | None = None, refresh: bool = False) -> pa.Table:
    """Extract transactions for a season."""
    return get_default_source().transactions(season=season, refresh=refresh)


def get_draft(year: int | None = None, refresh: bool = False) -> pa.Table:
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
