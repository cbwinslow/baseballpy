"""Parse Retrosheet's game-log field guide (``glfields.txt``) into per-column descriptions.

The guide lists 161 positional fields as ``<n>`` or ``<a>-<b>`` entries; the ``gamelogs`` schema
keeps the same order, so field number ``n`` is column ``n - 1``. Ranges are expanded by structure
read from the document itself (enumerated item lists, "ID and name", "X and Y" pairs, starting
player triples); nothing is described that the document does not say.
"""

import re

_ENTRY = re.compile(r"^\s{0,6}(?P<a>\d+)(?:-(?P<b>\d+))?\s{2,}(?P<head>\S.*)$")
_ITEM_INDENT = 13  # enumerated items are indented deeper than the entry text


class Entry:
    """One ``<a>[-<b>]`` entry: its heading line and its enumerated items."""

    def __init__(self, first: int, last: int, head: str) -> None:
        """Create an entry covering fields ``first``..``last``."""
        self.first, self.last, self.head = first, last, head
        self.items: list[str] = []
        self.notes: list[str] = []

    @property
    def size(self) -> int:
        """Number of fields covered."""
        return self.last - self.first + 1


def parse(text: str) -> list[Entry]:
    """Entries of the guide in document order."""
    entries: list[Entry] = []
    for line in text.splitlines():
        if (m := _ENTRY.match(line)) and not line.startswith(" " * 8):
            a, b = int(m["a"]), int(m["b"] or m["a"])
            entries.append(Entry(a, b, m["head"].strip()))
        elif entries and line.strip():
            current = entries[-1]
            enumerated = current.head.rstrip().endswith(":") or "(in order)" in current.head
            deep = len(line) - len(line.lstrip()) >= _ITEM_INDENT
            if enumerated and deep and not line.strip().startswith(('"', "yyyymmdd")):
                current.items.append(line.strip())
            else:
                current.notes.append(line.strip())
    return entries


def _short(text: str) -> str:
    text = re.sub(r"\s+", " ", re.split(r"\.\s", text)[0]).strip().rstrip(".:")
    return text[:200]


def _pair(head: str) -> tuple[str, str] | None:
    """``"Visiting and home team score"`` -> (``Visiting team score``, ``Home team score``)."""
    m = re.match(r"^(\w+) and (\w+) (.+)$", head)
    return (f"{m[1]} {m[3]}", f"{m[2].capitalize()} {m[3]}") if m else None


def describe(entries: list[Entry], count: int = 161) -> dict[int, str]:
    """``{field number: description}`` for fields ``1..count``."""
    out: dict[int, str] = {}
    last_items: dict[int, Entry] = {}
    for e in entries:
        head = re.sub(r"\s*\(.*?\)\s*$", "", re.split(r"\.\s", e.head)[0]).strip()
        if e.size == 1:
            out[e.first] = _short(head if not e.head.endswith(":") else e.head)
            continue
        if e.items:
            last_items[e.size] = e
        source = e if e.items else last_items.get(e.size)
        subject = re.sub(r"\s*\(.*$", "", head)
        if source is not None and "statistics" in head:
            for i, item in enumerate(source.items[: e.size]):
                out[e.first + i] = f"{subject.removesuffix(' statistics')}: {_short(item)}"
        elif head.endswith(" ID and name") or " ID and name" in head:
            who = head.split(" ID and name")[0]
            out[e.first], out[e.first + 1] = f"{who} ID", f"{who} name"
        elif "ID, name and defensive position" in head:
            who = head.split(" ID, name")[0]
            for i in range(e.size):
                slot = i // 3 + 1
                part = ("ID", "name", "defensive position")[i % 3]
                out[e.first + i] = f"{who}, batting order {slot}: {part}"
        elif (pair := _pair(head)) is not None and e.size == 2:
            out[e.first], out[e.first + 1] = pair
        elif " and " in head and e.size == 2:
            left, right = head.split(" and ", 1)
            out[e.first] = left
            out[e.first + 1] = f"{left.split()[0]} {right}"
    return {n: t for n, t in out.items() if 1 <= n <= count}
