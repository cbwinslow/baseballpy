"""Re-probe the games listed in ``unavailable_games.json`` (B-404): one request per game, through the shared client.

Usage: ``uv run python scripts/probe_unavailable_games.py``. It prints one line per game and exits 1 when a game
answers 200 again (remove it from the JSON file, then ingest it). It needs the network and asks the provider once per
listed game (the first URL of the entry), so run it by hand now and then, not in a loop.
"""

import sys

from baseballpy.core.http import HttpStatusError, get_http_client
from baseballpy.sources.mlb_api.game_segments import known_unavailable_games


def verdict(listed_status: int, now_status: int) -> str:
    """What a probe means: the game still fails the way it was listed, or it answers again."""
    if now_status == 200:
        return "ANSWERS AGAIN: remove it from unavailable_games.json"
    if now_status == listed_status:
        return "still unavailable"
    return f"now answers HTTP {now_status} (listed as {listed_status}): look at it"


def main() -> int:
    """Probe every listed game once; the exit code is 1 when any answers again."""
    http = get_http_client()
    again = 0
    for pk, entry in sorted(known_unavailable_games().items()):
        url = entry["urls"][1]  # the boxscore: small, and the first URL that decides a game
        try:
            status = http.get_sync(url, allow=(200, 404, 500)).status
        except HttpStatusError as exc:
            status = exc.status
        text = verdict(int(entry["status"]), status)
        print(f"{pk}: HTTP {status} {text}")
        again += status == 200
    return 1 if again else 0


if __name__ == "__main__":
    sys.exit(main())
