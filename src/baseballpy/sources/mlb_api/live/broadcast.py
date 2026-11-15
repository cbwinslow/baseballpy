"""The first broadcast of live events (ADR 137): one JSON line per event, appended to a file any program can follow.

``baseballpy live --jsonl FILE`` writes each event the moment the supervisor receives it, as one whole line (a single
``write`` call, flushed), so ``tail -f``, a Python loop or a model process sees complete lines and never half of one.
The file is opened for append: a restart continues it. The line holds the typed fields of ``LiveEvent.to_dict`` plus
``season``; the raw payloads stay in the journal. A websocket or SSE server needs a new library and an ADR (design
section 6); this file needs none.
"""

from pathlib import Path
from typing import IO

import msgspec

from baseballpy.sources.mlb_api.stream import LiveEvent


class JsonlBroadcast:
    """Appends live events to a JSON-lines file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle: IO[bytes] = path.open("ab")
        self._encoder = msgspec.json.Encoder()

    def write(self, season: int, event: LiveEvent) -> None:
        """Append one event as a line; it is flushed before this returns."""
        line = self._encoder.encode({**event.to_dict(), "season": season}) + b"\n"
        self._handle.write(line)
        self._handle.flush()

    def close(self) -> None:
        """Close the file."""
        self._handle.close()
