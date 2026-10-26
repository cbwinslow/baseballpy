"""High-performance msgspec models for MLB Stats API JSON payloads."""

import msgspec


class PitchCoordinates(msgspec.Struct, omit_defaults=True):
    pX: float | None = None
    pZ: float | None = None
    x: float | None = None
    y: float | None = None
    szTop: float | None = None
    szBottom: float | None = None


class PitchDetails(msgspec.Struct, omit_defaults=True):
    startSpeed: float | None = None
    endSpeed: float | None = None
    type: msgspec.Struct | dict[str, str] | None = None
    code: str | None = None
    description: str | None = None
    call: msgspec.Struct | dict[str, str] | None = None


class Count(msgspec.Struct, omit_defaults=True):
    balls: int = 0
    strikes: int = 0
    outs: int = 0


class PlayEvent(msgspec.Struct, omit_defaults=True):
    index: int = 0
    isPitch: bool = False
    type: str | None = None
    pitchData: msgspec.Struct | dict[str, msgspec.Raw] | None = None
    details: msgspec.Struct | dict[str, msgspec.Raw] | None = None
    count: Count | None = None
    pitchNumber: int | None = None
    startTime: str | None = None
    endTime: str | None = None


class MatchupPlayer(msgspec.Struct, omit_defaults=True):
    id: int = 0
    fullName: str = ""


class Matchup(msgspec.Struct, omit_defaults=True):
    batter: MatchupPlayer | None = None
    pitcher: MatchupPlayer | None = None


class About(msgspec.Struct, omit_defaults=True):
    atBatIndex: int = 0
    halfInning: str = "top"
    inning: int = 1
    isTopInning: bool = True


class Result(msgspec.Struct, omit_defaults=True):
    event: str | None = None
    eventType: str | None = None
    description: str | None = None


class Play(msgspec.Struct, omit_defaults=True):
    result: Result | None = None
    about: About | None = None
    matchup: Matchup | None = None
    count: Count | None = None
    playEvents: list[msgspec.Raw] = []


class LivePlays(msgspec.Struct, omit_defaults=True):
    allPlays: list[msgspec.Raw] = []
    currentPlay: msgspec.Raw | None = None


class LiveData(msgspec.Struct, omit_defaults=True):
    plays: LivePlays | None = None


class MetaData(msgspec.Struct, omit_defaults=True):
    timeStamp: str | None = None


class LiveFeed(msgspec.Struct, omit_defaults=True):
    gamePk: int = 0
    metaData: MetaData | None = None
    liveData: LiveData | None = None
