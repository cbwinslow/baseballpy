"""Tests for MLB Stats API extraction, live streaming diffing, and PyArrow normalization."""

from pathlib import Path

import httpx
import pyarrow as pa
import pytest
import respx

from baseballpy.core.config import CacheConfig
from baseballpy.sources.mlb_api.api import MlbApiSource
from baseballpy.sources.mlb_api.extractor import MLB_BASE_URL, MlbApiExtractor
from baseballpy.sources.mlb_api.normalizer import MlbApiNormalizer
from baseballpy.sources.mlb_api.stream import GamedayLiveStreamer


def test_normalize_schedule() -> None:
    normalizer = MlbApiNormalizer()
    fake_schedule = {
        "dates": [
            {
                "date": "2024-04-01",
                "games": [
                    {
                        "gamePk": 745789,
                        "gameType": "R",
                        "season": "2024",
                        "gameNumber": 1,
                        "doubleHeader": "N",
                        "status": {"statusCode": "F", "detailedState": "Final"},
                        "teams": {
                            "away": {"team": {"id": 110, "name": "Baltimore Orioles"}, "score": 3},
                            "home": {"team": {"id": 111, "name": "Boston Red Sox"}, "score": 5},
                        },
                        "venue": {"id": 3, "name": "Fenway Park"},
                    }
                ],
            }
        ]
    }

    table = normalizer.normalize_schedule(fake_schedule)
    assert isinstance(table, pa.Table)
    assert len(table) == 1
    assert table.schema.field("game_pk").type == pa.int32()
    assert table.schema.field("game_date").type == pa.date32()
    assert table["game_pk"].to_pylist() == [745789]
    assert table["away_team_name"].to_pylist() == ["Baltimore Orioles"]
    assert table["home_score"].to_pylist() == [5]


def test_normalize_boxscore() -> None:
    normalizer = MlbApiNormalizer()
    fake_boxscore = {
        "teams": {
            "away": {
                "team": {"id": 110},
                "players": {
                    "ID660271": {
                        "person": {"id": 660271, "fullName": "Shohei Ohtani"},
                        "position": {"abbreviation": "DH"},
                        "battingOrder": "100",
                        "stats": {
                            "batting": {
                                "atBats": 4,
                                "runs": 2,
                                "hits": 3,
                                "doubles": 1,
                                "triples": 0,
                                "homeRuns": 1,
                                "rbi": 2,
                                "baseOnBalls": 1,
                                "strikeOuts": 0,
                            }
                        },
                    }
                },
            },
            "home": {
                "team": {"id": 111},
                "players": {
                    "ID543037": {
                        "person": {"id": 543037, "fullName": "Gerrit Cole"},
                        "position": {"abbreviation": "P"},
                        "stats": {
                            "pitching": {
                                "inningsPitched": "6.0",
                                "hits": 4,
                                "runs": 2,
                                "earnedRuns": 2,
                                "baseOnBalls": 1,
                                "strikeOuts": 8,
                                "homeRuns": 1,
                                "pitchesThrown": 95,
                                "strikes": 64,
                            }
                        },
                    }
                },
            },
        }
    }

    batting, pitching = normalizer.normalize_boxscore(fake_boxscore, game_pk=745789)
    assert len(batting) == 1
    assert batting["player_name"].to_pylist() == ["Shohei Ohtani"]
    assert batting["hr"].to_pylist() == [1]

    assert len(pitching) == 1
    assert pitching["player_name"].to_pylist() == ["Gerrit Cole"]
    assert pitching["so"].to_pylist() == [8]
    assert pitching["ip"].to_pylist()[0] == pytest.approx(6.0)


@pytest.mark.asyncio
async def test_gameday_live_streamer_diffing() -> None:
    fake_live_payload = {
        "gamePk": 745789,
        "gameData": {"status": {"abstractGameState": "Final"}},
        "liveData": {
            "plays": {
                "allPlays": [
                    {
                        "about": {"atBatIndex": 0, "inning": 1, "isTopInning": True},
                        "matchup": {
                            "batter": {"id": 660271, "fullName": "Shohei Ohtani"},
                            "pitcher": {"id": 543037, "fullName": "Gerrit Cole"},
                        },
                        "playEvents": [
                            {
                                "index": 0,
                                "isPitch": True,
                                "pitchData": {
                                    "startSpeed": 98.4,
                                    "endSpeed": 90.1,
                                    "coordinates": {"pX": -0.2, "pZ": 2.5, "szTop": 3.4, "szBottom": 1.5},
                                },
                                "details": {
                                    "type": {"code": "FF"},
                                    "call": {"code": "C"},
                                    "description": "Called Strike",
                                },
                                "count": {"balls": 0, "strikes": 1, "outs": 0},
                                "startTime": "2024-04-01T17:05:00Z",
                            },
                            {
                                "index": 1,
                                "isPitch": True,
                                "pitchData": {
                                    "startSpeed": 99.1,
                                    "endSpeed": 91.0,
                                    "coordinates": {"pX": 0.1, "pZ": 2.8, "szTop": 3.4, "szBottom": 1.5},
                                },
                                "details": {
                                    "type": {"code": "FF"},
                                    "call": {"code": "X"},
                                    "description": "In play, run(s)",
                                    "event": "Home Run",
                                },
                                "count": {"balls": 0, "strikes": 2, "outs": 0},
                                "startTime": "2024-04-01T17:05:25Z",
                            },
                        ],
                    }
                ]
            }
        }
    }

    async with httpx.AsyncClient() as client:
        with respx.mock:
            respx.get("https://statsapi.mlb.com/api/v1.1/game/745789/feed/live").mock(
                return_value=httpx.Response(200, json=fake_live_payload, headers={"ETag": "W/'123'"})
            )

            streamer = GamedayLiveStreamer(game_pk=745789, poll_interval=0.01, client=client)
            events = [ev async for ev in streamer.stream_events()]

            assert len(events) == 2
            assert events[0]["pitch_type"] == "FF"
            assert events[0]["description"] == "Called Strike"
            assert events[1]["event"] == "Home Run"
            assert events[1]["start_speed"] == pytest.approx(99.1)


@respx.mock
def test_mlb_extractor_caching(tmp_path: Path) -> None:
    cache_config = CacheConfig(base_dir=tmp_path)
    extractor = MlbApiExtractor(cache_config=cache_config)

    fake_teams = {
        "teams": [
            {
                "id": 147,
                "name": "New York Yankees",
                "abbreviation": "NYY",
                "league": {"id": 103, "name": "American League"},
                "division": {"id": 201, "name": "American League East"},
                "venue": {"id": 3313, "name": "Yankee Stadium"},
                "active": True,
            }
        ]
    }

    respx.get(f"{MLB_BASE_URL}/v1/teams").mock(return_value=httpx.Response(200, json=fake_teams))

    # First fetch writes to cache
    table = extractor.extract_teams()
    assert len(table) == 1
    assert table["team_name"].to_pylist() == ["New York Yankees"]
    assert extractor.manifest.is_completed("teams_mlb")

    # Second fetch reads from cache
    respx.get(f"{MLB_BASE_URL}/v1/teams").mock(return_value=httpx.Response(500))
    cached = extractor.extract_teams(refresh=False)
    assert len(cached) == 1


@respx.mock
def test_mlb_source_orchestrator(tmp_path: Path) -> None:
    cache_config = CacheConfig(base_dir=tmp_path)
    source = MlbApiSource(cache_config=cache_config)

    fake_standings = {
        "records": [
            {
                "division": {"id": 201, "name": "American League East"},
                "teamRecords": [
                    {
                        "team": {"id": 147, "name": "New York Yankees"},
                        "wins": 94,
                        "losses": 68,
                        "winningPercentage": ".580",
                        "gamesBack": "-",
                        "runDifferential": 147,
                        "streak": {"streakCode": "W3"},
                    }
                ],
            }
        ]
    }

    respx.get(f"{MLB_BASE_URL}/v1/standings").mock(return_value=httpx.Response(200, json=fake_standings))

    table = source.standings(2024)
    assert len(table) == 1
    assert table["wins"].to_pylist() == [94]
    assert table["win_pct"].to_pylist()[0] == pytest.approx(0.580)
