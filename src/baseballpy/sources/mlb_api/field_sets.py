"""Named projections of a game's ``feed/live`` document, kept as data (ADR 54).

The provider's ``fields=`` parameter selects which **key names** an answer carries. Two measured rules
shape the table below:

- a projection needs every parent key: ``fields=status,detailedState,linescore,runs`` answered 17 bytes
  because neither ``gameData`` nor ``liveData`` was named, while the same keys with their ancestors
  answered correctly, so a set is written as dotted paths and :func:`expand_fields` adds each segment;
- a name matches **globally**, not by path, so naming a key that occurs everywhere (``description``,
  ``allPlays``) pulls in a whole branch. Every set here was measured on game ``745000``; a set that is
  not clearly smaller than the 663,043-byte complete document is not shipped (a ``plays`` set measured
  144,027 bytes and is deliberately absent).

``fields=`` is ignored by ``feed/live/diffPatch`` and a patch addresses paths a projection lacks, so a
projection is only ever used for a single snapshot, never for the polling stream.
"""

from collections.abc import Mapping, Sequence

#: the document containers of the live feed; a projection that names a path inside one must name it
DOCUMENT_CONTAINERS = ("gameData", "liveData", "metaData")

#: named projection -> dotted paths of the values it promises. Measured bytes on game 745000:
#: state 141, score 368, pitch 4,377, boxscore 12,500, decisions 94 (design.md of
#: ``mlb-live-feed-projection``); the key names each set expands to are the ones that were measured.
LIVE_FIELD_SETS: Mapping[str, tuple[str, ...]] = {
    "state": (
        "gameData.status.abstractGameState",
        "gameData.status.detailedState",
        "gameData.status.codedGameState",
        "metaData.timeStamp",
    ),
    "score": (
        "gameData.status.abstractGameState",
        "gameData.status.detailedState",
        "liveData.linescore.currentInning",
        "liveData.linescore.currentInningOrdinal",
        "liveData.linescore.inningState",
        "liveData.linescore.isTopInning",
        "liveData.linescore.outs",
        "liveData.linescore.balls",
        "liveData.linescore.strikes",
        "liveData.linescore.teams.away.runs",
        "liveData.linescore.teams.away.hits",
        "liveData.linescore.teams.away.errors",
        "liveData.linescore.teams.away.leftOnBase",
        "liveData.linescore.teams.home.runs",
        "liveData.linescore.teams.home.hits",
        "liveData.linescore.teams.home.errors",
        "liveData.linescore.teams.home.leftOnBase",
    ),
    "pitch": (
        "liveData.plays.currentPlay.about.atBatIndex",
        "liveData.plays.currentPlay.about.inning",
        "liveData.plays.currentPlay.about.halfInning",
        "liveData.plays.currentPlay.about.isTopInning",
        "liveData.plays.currentPlay.count.balls",
        "liveData.plays.currentPlay.count.strikes",
        "liveData.plays.currentPlay.count.outs",
        "liveData.plays.currentPlay.matchup.batter.id",
        "liveData.plays.currentPlay.matchup.batter.fullName",
        "liveData.plays.currentPlay.matchup.pitcher.id",
        "liveData.plays.currentPlay.matchup.pitcher.fullName",
        "liveData.plays.currentPlay.result.event",
        "liveData.plays.currentPlay.result.description",
        "liveData.plays.currentPlay.playEvents.index",
        "liveData.plays.currentPlay.playEvents.isPitch",
        "liveData.plays.currentPlay.playEvents.details.type.code",
        "liveData.plays.currentPlay.playEvents.details.description",
        "liveData.plays.currentPlay.playEvents.pitchData.startSpeed",
        "liveData.plays.currentPlay.playEvents.pitchData.endSpeed",
        "liveData.plays.currentPlay.playEvents.pitchData.zone",
        "liveData.plays.currentPlay.playEvents.pitchData.coordinates.pX",
        "liveData.plays.currentPlay.playEvents.pitchData.coordinates.pZ",
        "liveData.plays.currentPlay.playEvents.pitchData.breaks.spinRate",
        "liveData.plays.currentPlay.playEvents.hitData.launchSpeed",
        "liveData.plays.currentPlay.playEvents.hitData.launchAngle",
        "liveData.plays.currentPlay.playEvents.hitData.totalDistance",
        "liveData.plays.currentPlay.playEvents.hitData.trajectory",
    ),
    "boxscore": (
        "liveData.boxscore.teams.away.team.id",
        "liveData.boxscore.teams.away.teamStats.batting.runs",
        "liveData.boxscore.teams.away.teamStats.batting.hits",
        "liveData.boxscore.teams.away.teamStats.batting.homeRuns",
        "liveData.boxscore.teams.home.team.id",
        "liveData.boxscore.teams.home.teamStats.batting.runs",
        "liveData.boxscore.teams.home.teamStats.batting.hits",
        "liveData.boxscore.teams.home.teamStats.batting.homeRuns",
    ),
    "decisions": (
        "liveData.decisions.winner.id",
        "liveData.decisions.loser.id",
        "liveData.decisions.save.id",
    ),
}


def set_names() -> tuple[str, ...]:
    """The shipped set names, in table order (for error messages and the CLI)."""
    return tuple(LIVE_FIELD_SETS)


def expand_fields(fields: str | Sequence[str]) -> tuple[str, ...]:
    """Resolve ``fields`` to the flat, de-duplicated key names the provider expects on the wire.

    A bare string without a comma or a dot is a **set name**; an unknown one raises ``ValueError``
    listing the valid names. A sequence, or a string containing a comma or a dot, is a **raw
    projection**. Every dotted path contributes all of its segments, parents first, each name once.
    """
    paths = _projection(fields)
    keys: list[str] = []
    seen: set[str] = set()
    for path in paths:
        for segment in path.split("."):
            name = segment.strip()
            if name and name not in seen:
                seen.add(name)
                keys.append(name)
    if not keys:
        raise ValueError("an empty field projection selects nothing")
    return tuple(keys)


def required_containers(keys: Sequence[str]) -> tuple[str, ...]:
    """The document containers a projection names; a decoded answer missing one is a failed snapshot."""
    return tuple(name for name in DOCUMENT_CONTAINERS if name in keys)


def _projection(fields: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(fields, str):
        if "," not in fields and "." not in fields:
            name = fields.strip()
            try:
                return LIVE_FIELD_SETS[name]
            except KeyError:
                raise ValueError(
                    f"unknown field set {name!r}; valid names: {', '.join(set_names())}. "
                    "Pass a sequence (or a dotted path) for a raw key list."
                ) from None
        paths: tuple[str, ...] = tuple(fields.split(","))
    else:
        paths = tuple(fields)
    cleaned = tuple(path.strip() for path in paths if path and path.strip())
    if not cleaned:
        raise ValueError("an empty field projection selects nothing")
    return cleaned
