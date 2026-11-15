"""CLI: ``baseballpy live`` follows every MLB game while it is played and keeps its rows in the lake (ADR 137, 140)."""

import asyncio
from datetime import UTC, datetime

import click
from rich.console import Console
from rich.table import Table

from baseballpy.core.config import LakeConfig, StreamingConfig
from baseballpy.core.http import get_http_client
from baseballpy.core.memguard import MemoryGovernor
from baseballpy.sources.mlb_api.live.schedule import MlbScheduleSource
from baseballpy.sources.mlb_api.live.sink import LiveGameSink
from baseballpy.sources.mlb_api.live.supervisor import LiveSupervisor, ScheduledGame, is_due
from baseballpy.sources.mlb_api.stream import GamedayLiveStreamer

console = Console()

#: a rain delay can last hours and a delay produces no events; the stream's own idle limit must outlast it
MIN_IDLE_MINUTES = 360


def _sports(text: str) -> tuple[int, ...]:
    try:
        ids = tuple(dict.fromkeys(int(part) for part in text.split(",") if part.strip()))
    except ValueError as exc:
        raise click.BadParameter(
            f"{text!r}: use comma-separated sport ids, e.g. 1 or 1,11"
        ) from exc
    if not ids:
        raise click.BadParameter("name at least one sport id")
    return ids


async def _games_now(source: MlbScheduleSource) -> list[ScheduledGame]:
    today = datetime.now(UTC).date()
    return [
        *await source.games(today.fromordinal(today.toordinal() - 1)),
        *await source.games(today),
    ]


def _show_games(games: list[ScheduledGame], lead_minutes: int) -> None:
    now = datetime.now(UTC)
    table = Table(title="Games now (UTC today and yesterday)")
    for column in ("game_pk", "state", "starts (UTC)", "followed now"):
        table.add_column(column)
    for game in games:
        start = game.start_utc.strftime("%Y-%m-%d %H:%M") if game.start_utc else "?"
        table.add_row(
            str(game.game_pk), game.state, start, "yes" if is_due(game, now, lead_minutes) else "no"
        )
    console.print(table)


@click.command("live")
@click.option(
    "--sports",
    default="1",
    show_default=True,
    help="Levels to follow: sport ids (1 = the major leagues).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="List the games it would follow now and stop (one schedule request).",
)
@click.option(
    "--max-games",
    type=int,
    default=None,
    help="Most games followed at once (default: the setting).",
)
@click.option(
    "--commit-seconds", type=float, default=None, help="Seconds between writes to the lake."
)
def live_cmd(
    sports: str, dry_run: bool, max_games: int | None, commit_seconds: float | None
) -> None:
    """Follow the games being played and keep their rows in the lake (Ctrl-C stops it cleanly).

    Every poll answer is kept in a journal under raw/mlb_api/_live; the rows are readable at once as the dataset
    game_live_events (view mlb_game_live_events). After a game, the normal `ingest -d games` stores it in the
    long-term tables. Settings: BASEBALLPY_STREAM_* (poll interval, lead time, queue size, restarts).
    """
    levels = _sports(sports)
    settings = StreamingConfig()
    updates: dict[str, object] = {"journal": True}
    if max_games is not None:
        updates["max_live_games"] = max_games
    if commit_seconds is not None:
        updates["commit_seconds"] = commit_seconds
    updates["max_inactivity_minutes"] = max(settings.max_inactivity_minutes, MIN_IDLE_MINUTES)
    config = settings.model_copy(update=updates)
    source = MlbScheduleSource(get_http_client(), levels)
    if dry_run:
        _show_games(asyncio.run(_games_now(source)), config.lead_minutes)
        return
    lake = LakeConfig()
    streamer = GamedayLiveStreamer(config=config, lake=lake)
    supervisor = LiveSupervisor(
        sink=LiveGameSink(lake),
        schedule=source,
        stream=streamer.stream_live_events,
        config=config,
        governor=MemoryGovernor(),
        destination=str(lake.processed_dir("mlb_api", "game_live_events")),
    )
    console.print(
        f"Following games (sports {','.join(map(str, levels))}); rows go to {lake.home}. Ctrl-C stops it."
    )

    async def main() -> None:
        stop = asyncio.Event()
        report = await supervisor.run(stop)
        console.print(report)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print(f"Stopped. {supervisor.report}")


def register_live_command(main: click.Group) -> None:
    """Attach ``live`` to the main group."""
    main.add_command(live_cmd, "live")


__all__ = ["live_cmd", "register_live_command"]
