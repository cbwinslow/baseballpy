"""CLI command for streaming live MLB Gameday play events to stdout, DuckDB, or JSONL."""

import asyncio
import json
import types
import typing
from pathlib import Path

import click
import msgspec
import pyarrow as pa
from rich.console import Console

from baseballpy.sinks.duckdb import DuckDBSink
from baseballpy.sources.mlb_api.stream import GamedayLiveStreamer, LiveEvent

console = Console()


_ARROW_TYPES: dict[type, pa.DataType] = {
    int: pa.int64(),
    float: pa.float64(),
    str: pa.string(),
    bool: pa.bool_(),
}


def live_event_schema() -> pa.Schema:
    """Arrow schema of ``LiveEvent.to_dict()``, derived from the struct's own annotations.

    Declared types (not the first batch's values) fix the columns, so a batch whose optional
    fields are all ``None`` still writes typed columns the next batch can upsert into.
    """
    hints = typing.get_type_hints(LiveEvent)
    fields: list[pa.Field] = []
    for info in msgspec.structs.fields(LiveEvent):
        if info.name in ("raw_play", "raw_event"):
            continue
        hint = hints[info.name]
        if typing.get_origin(hint) in (typing.Union, types.UnionType):
            hint = next(a for a in typing.get_args(hint) if a is not type(None))
        fields.append(pa.field(info.name, _ARROW_TYPES[hint]))
    return pa.schema(fields)


def make_streamer(poll_interval: float | None = None) -> GamedayLiveStreamer:
    """Instantiate a GamedayLiveStreamer with the configured poll interval.

    Args:
        poll_interval: Optional poll interval override in seconds.

    Returns:
        A GamedayLiveStreamer instance.
    """
    return GamedayLiveStreamer(poll_interval=poll_interval)


def _format_event(event: LiveEvent) -> str:
    """Format a single LiveEvent as a human-readable one-line rich summary.

    Args:
        event: The live event to format.

    Returns:
        Formatted rich string summary.
    """
    half = "Top" if event.is_top_inning else "Bot"
    loc = f"[{half} {event.inning} | {event.balls}-{event.strikes}, {event.outs} out]"
    if event.is_pitch:
        pitch_name = event.pitch_type or "Pitch"
        speed_str = f" {event.start_speed:.1f} mph" if event.start_speed is not None else ""
        desc = event.description or event.call_code or ""
        return (
            f"[cyan]{loc}[/cyan] [bold green]PITCH[/bold green]: {pitch_name}{speed_str} - {desc}"
        )
    if event.event_kind == "play_result":
        res = event.play_result or event.event or "Result"
        return f"[cyan]{loc}[/cyan] [bold yellow]RESULT[/bold yellow]: {res} - {event.description}"
    if event.event_kind == "half_inning_end":
        return f"[cyan]{loc}[/cyan] [bold magenta]INNING END[/bold magenta]: {event.description}"
    if event.event_kind == "game_status":
        return f"[dim]{loc}[/dim] [bold blue]STATUS[/bold blue]: {event.description or event.event or ''}"
    desc = event.description or event.event or event.event_type or event.event_kind
    return f"[cyan]{loc}[/cyan] [bold]{event.event_kind.upper()}[/bold]: {desc}"


async def _stream_loop(
    streamer: GamedayLiveStreamer,
    game_pk: int,
    replay: bool,
    jsonl_path: Path | None,
    duckdb_path: Path | None,
    table_name: str,
    max_events: int | None,
    as_json: bool,
) -> tuple[int, int]:
    """Consume the live event stream, persisting batches and printing summaries.

    Args:
        streamer: GamedayLiveStreamer instance.
        game_pk: MLBAM Game ID.
        replay: If True, bypass watermark and replay all events.
        jsonl_path: Optional path for appending JSONL records.
        duckdb_path: Optional DuckDB file path for upserting events.
        table_name: Destination DuckDB table name.
        max_events: Optional maximum number of events to process.
        as_json: If True, output JSON lines to stdout.

    Returns:
        Tuple of (events_seen, events_written).
    """
    seen_count = 0
    written_count = 0
    batch: list[LiveEvent] = []

    def flush_batch() -> None:
        nonlocal written_count
        if not batch:
            return
        if jsonl_path is not None:
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with open(jsonl_path, "a", encoding="utf-8") as handle:
                for ev in batch:
                    handle.write(json.dumps(ev.to_dict()) + "\n")
        if duckdb_path is not None:
            duckdb_path.parent.mkdir(parents=True, exist_ok=True)
            table = pa.Table.from_pylist([ev.to_dict() for ev in batch], schema=live_event_schema())
            DuckDBSink().write(
                table,
                destination=str(duckdb_path),
                table_name=table_name,
                mode="upsert",
                key_columns=("game_pk", "at_bat_index", "event_index"),
            )
        written_count += len(batch)
        batch.clear()

    try:
        async for event in streamer.stream_live_events(game_pk, resume=not replay):
            seen_count += 1
            if as_json:
                click.echo(json.dumps(event.to_dict()))
            else:
                console.print(_format_event(event))

            if jsonl_path is not None or duckdb_path is not None:
                batch.append(event)
                if len(batch) >= 50:
                    flush_batch()

            if max_events is not None and seen_count >= max_events:
                break
    finally:
        flush_batch()

    return seen_count, written_count


@click.command("stream")
@click.argument("game_pk", type=int)
@click.option(
    "--replay",
    is_flag=True,
    help="Ignore stored watermark and emit every event again.",
)
@click.option(
    "--jsonl",
    "jsonl_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Append events as JSON objects to this file.",
)
@click.option(
    "--duckdb",
    "duckdb_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Upsert events into a DuckDB file destination.",
)
@click.option(
    "--table",
    "table_name",
    type=str,
    default="live_events",
    show_default=True,
    help="Target table name when saving to DuckDB.",
)
@click.option(
    "--poll-interval",
    type=float,
    default=None,
    help="Polling interval override in seconds.",
)
@click.option(
    "--max-events",
    type=int,
    default=None,
    help="Stop streaming after processing N events.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Print events as JSON lines to stdout.",
)
@click.pass_context
def stream_cmd(
    ctx: click.Context,
    game_pk: int,
    replay: bool,
    jsonl_path: Path | None,
    duckdb_path: Path | None,
    table_name: str,
    poll_interval: float | None,
    max_events: int | None,
    as_json: bool,
) -> None:
    """Stream live pitch and play events for a game in real time or replay mode."""
    streamer = make_streamer(poll_interval)
    try:
        seen_count, written_count = asyncio.run(
            _stream_loop(
                streamer=streamer,
                game_pk=game_pk,
                replay=replay,
                jsonl_path=jsonl_path,
                duckdb_path=duckdb_path,
                table_name=table_name,
                max_events=max_events,
                as_json=as_json,
            )
        )
    except KeyboardInterrupt:
        ctx.exit(130)
    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    destinations: list[str] = []
    if jsonl_path is not None:
        destinations.append(str(jsonl_path))
    if duckdb_path is not None:
        destinations.append(f"{duckdb_path} ({table_name})")
    dest_str = ", ".join(destinations) if destinations else "none"

    if not as_json:
        console.print(
            f"Stream completed: {seen_count} events seen, {written_count} events written, destination(s): {dest_str}"
        )

    ctx.exit(0)


def register_stream_command(main: click.Group) -> None:
    """Register the stream command on the main Click command group.

    Args:
        main: Top-level Click command group.
    """
    main.add_command(stream_cmd, "stream")


__all__ = [
    "make_streamer",
    "register_stream_command",
    "stream_cmd",
]
