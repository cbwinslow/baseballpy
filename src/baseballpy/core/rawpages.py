"""Distinct records in a source's raw answer pages, for the round-trip check of JSON sources.

Kalshi and Polymarket keep every answer they received as one gzip of JSON lines per request series (the shared
``RawLog``: one line per page, the page text in ``body``). The cell check cannot read that, so the check counts
instead: the distinct keys that all the raw pages hold are the rows the processed table must have (a record seen on
two pages, or live and archived, is stored once).
"""

import gzip
import json
from collections.abc import Callable, Hashable, Iterable, Iterator, Sequence
from pathlib import Path

from baseballpy.core.config import LakeConfig


def page_lines(folder: Path) -> Iterator[tuple[dict[str, object], dict[str, object]]]:
    """``(log line, decoded body)`` of every page in every ``*.jsonl.gz`` file of ``folder``.

    The log line carries the request (``route``, ``ticker``, ``page``) next to the body, so a count rule can
    read a key that only the request knows (the token a price history belongs to).
    """
    if not folder.is_dir():
        return
    for path in sorted(folder.glob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for text in handle:
                if not text.strip():
                    continue
                line = json.loads(text)
                body = line.get("body")
                if isinstance(body, str):
                    decoded = json.loads(body)
                    if isinstance(decoded, dict):
                        yield line, decoded


def page_bodies(folder: Path) -> Iterator[dict[str, object]]:
    """The decoded body of every page in every ``*.jsonl.gz`` file of ``folder``."""
    for _, body in page_lines(folder):
        yield body


def distinct_tuples(
    config: LakeConfig,
    dataset_folder: tuple[str, str],
    keys_of: Callable[[dict[str, object], dict[str, object]], Iterable[Hashable]],
) -> int:
    """Distinct keys that ``keys_of(log line, body)`` finds in all the pages of one raw folder.

    ``keys_of`` knows the shape of a source's pages (several routes can share a folder); a key seen on two
    pages counts once, like the row the table keeps.
    """
    source, dataset = dataset_folder
    seen: set[Hashable] = set()
    for line, body in page_lines(config.raw_dir(source, dataset)):
        seen.update(keys_of(line, body))
    return len(seen)


def tuples_counter(
    source: str,
    folder: str,
    keys_of: Callable[[dict[str, object], dict[str, object]], Iterable[Hashable]],
) -> Callable[[LakeConfig, int], int]:
    """:func:`distinct_tuples` of one raw folder, in the shape the round-trip check registers."""

    def count(config: LakeConfig, _season: int) -> int:
        return distinct_tuples(config, (source, folder), keys_of)

    return count


def distinct_keys(
    config: LakeConfig,
    dataset_folder: tuple[str, str],
    list_name: str,
    key: str,
    nested: Sequence[str] = (),
) -> int:
    """Distinct ``key`` values of the records listed under ``list_name`` in the pages of one raw folder.

    ``nested`` names a list inside each record whose items are counted instead (Polymarket markets sit inside events).
    """
    source, dataset = dataset_folder
    seen: set[object] = set()
    for body in page_bodies(config.raw_dir(source, dataset)):
        records = body.get(list_name)
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            items: list[object] = [record]
            for name in nested:
                inner = record.get(name)
                items = [i for i in inner if isinstance(i, dict)] if isinstance(inner, list) else []
            seen.update(i[key] for i in items if isinstance(i, dict) and key in i)
    return len(seen)


def pages_counter(
    source: str, folder: str, list_name: str, key: str, nested: Sequence[str] = ()
) -> Callable[[LakeConfig, int], int]:
    """:func:`distinct_keys` of one raw folder, in the shape the round-trip check registers."""

    def count(config: LakeConfig, _season: int) -> int:
        return distinct_keys(config, (source, folder), list_name, key, nested)

    return count


__all__ = [
    "distinct_keys",
    "distinct_tuples",
    "page_bodies",
    "page_lines",
    "pages_counter",
    "tuples_counter",
]
