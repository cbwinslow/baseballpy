"""Generic JSON -> flat records for the MLB Stats API (no per-endpoint parsing code).

A response is walked along a ``records_path`` (``"*"`` = every element of a list); each record is a
dict whose nested objects are flattened to ``a.b.c`` keys. Scalar fields of the objects traversed on
the way (e.g. ``dates[*].date``) are carried into the record under ``<list key>.<field>`` so no
context is lost. Arrays inside a record are kept as JSON text (their element shape is not stable
enough to type), which keeps every upstream field while giving the table a flat, typed schema.
"""

import json
import re
from collections.abc import Iterable, Iterator
from typing import Any

Scalar = str | int | float | bool | None


def _flatten(obj: dict[str, Any], prefix: str, out: dict[str, Scalar], skip: str | None) -> None:
    for key, value in obj.items():
        if skip is not None and key == skip and not prefix:
            continue
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            _flatten(value, f"{name}.", out, None)
        elif isinstance(value, list):
            out[name] = (
                json.dumps(value, separators=(",", ":"), ensure_ascii=False) if value else None
            )
        else:
            out[name] = value


def flatten_record(obj: dict[str, Any]) -> dict[str, Scalar]:
    """Flatten nested objects to dotted keys; lists become JSON text (empty list -> ``None``)."""
    out: dict[str, Scalar] = {}
    _flatten(obj, "", out, None)
    return out


def iter_records(payload: Any, path: tuple[str, ...]) -> Iterator[dict[str, Scalar]]:
    """Yield flattened records found at ``path`` (``"*"`` fans out over list elements).

    A path that does not exist in the payload yields nothing; a payload whose shape contradicts the
    path (a scalar where a list/dict was expected) raises ``ValueError`` so a changed API fails
    loudly instead of producing an empty table.
    """
    yield from _walk(payload, path, {}, "")


def _walk(
    node: Any, path: tuple[str, ...], carry: dict[str, Scalar], label: str
) -> Iterator[dict[str, Scalar]]:
    if not path:
        if isinstance(node, list):
            for item in node:
                yield from _emit(item, carry)
        else:
            yield from _emit(node, carry)
        return
    head, rest = path[0], path[1:]
    if head == "*":
        if not isinstance(node, list):
            raise ValueError(f"expected a list at {label or 'root'}, got {type(node).__name__}")
        for element in node:
            if isinstance(element, dict):
                nxt = rest[0] if rest and rest[0] != "*" else None
                extra: dict[str, Scalar] = {}
                _flatten(element, "", extra, nxt)
                ctx = {f"{label}.{k}" if label else k: v for k, v in extra.items()}
                yield from _walk(element, rest, {**carry, **ctx}, label)
            else:
                yield from _walk(element, rest, carry, label)
        return
    if node is None:
        return
    if not isinstance(node, dict):
        raise ValueError(f"expected an object at {label or 'root'}, got {type(node).__name__}")
    if head not in node:
        return
    yield from _walk(node[head], rest, carry, head)


def _emit(item: Any, carry: dict[str, Scalar]) -> Iterator[dict[str, Scalar]]:
    if isinstance(item, dict):
        yield {**carry, **flatten_record(item)}
    elif item is not None:
        yield {**carry, "value": item}


def trim_payload(payload: Any, path: tuple[str, ...], keep: int) -> Any:
    """A copy of ``payload`` whose list at ``path`` keeps only the first ``keep`` elements.

    Used to build small fixtures from live responses while preserving every wrapper field.
    """
    if not path:
        return payload[:keep] if isinstance(payload, list) else payload
    head, rest = path[0], path[1:]
    if head == "*":
        if not isinstance(payload, list):
            return payload
        return [trim_payload(e, rest, keep) for e in payload[: max(keep, 1)]]
    if isinstance(payload, dict) and head in payload:
        return {**payload, head: trim_payload(payload[head], rest, keep)}
    return payload


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ISO_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})")
_INT32 = 2_000_000_000


def infer_type(values: Iterable[Scalar]) -> str | None:
    """Type name for a column of already-typed JSON scalars, or ``None`` if every value is NULL.

    bool < int < float; ISO dates -> ``date32``, ISO timestamps with a zone -> ``timestamp``;
    anything else (including a mix of kinds) is ``string``. Never narrower than ``int32``.
    """
    kinds: set[str] = set()
    big = False
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            kinds.add("bool")
        elif isinstance(value, int):
            kinds.add("int")
            big = big or abs(value) > _INT32
        elif isinstance(value, float):
            kinds.add("float")
        elif _ISO_TIMESTAMP.fullmatch(value):
            kinds.add("timestamp")
        elif _ISO_DATE.fullmatch(value):
            kinds.add("date")
        else:
            kinds.add("string")
    if not kinds:
        return None
    if kinds == {"bool"}:
        return "bool"
    if kinds == {"int"}:
        return "int64" if big else "int32"
    if kinds <= {"int", "float"}:
        return "float64"
    if kinds == {"timestamp"}:
        return "timestamp"
    if kinds == {"date"}:
        return "date32"
    return "string"
