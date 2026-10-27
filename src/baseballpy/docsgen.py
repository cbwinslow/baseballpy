"""Generate the per-dataset column dictionaries in ``docs/sources/<source>.md`` from the registry.

For every registered dataset a block delimited by ``<!-- BEGIN GENERATED:<source>.<dataset> -->`` /
``<!-- END GENERATED:... -->`` is rendered (view, partitioning, key, column | type | nullable |
upstream name | description). Descriptions live in ``docs/columns/<source>.json``::

    {"_sources": {"<key>": "<url or document>"},
     "*": {"<column>": {"text": "...", "source": "<key>", "authored": false}},
     "<dataset>": {"<column>": "text" | {"text": ..., "source": ...}}}

A dataset-specific entry wins over ``"*"`` (a source-wide default for a column name). Every
description cites a ``_sources`` key (provider metadata) or is flagged ``authored``; a column
without one renders ``TODO`` and is counted by :func:`description_coverage` (``docs coverage``;
the ratchet test fails when a source's described-column count drops below
``docs/columns/coverage_baseline.json``). A test regenerates and fails when the committed docs
are stale, so documentation cannot drift from the schemas.
"""

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa

from baseballpy.core.datasets import DATASETS, DatasetSpec
from baseballpy.core.schema_tools import FORMAT_KEY, UPSTREAM_KEY
from baseballpy.sources import catalog

HEADING = "## Dataset reference (generated)"
_BLOCK = re.compile(
    r"<!-- BEGIN GENERATED:(?P<key>[\w.]+) -->.*?<!-- END GENERATED:(?P=key) -->\n?", re.DOTALL
)


def _type_name(field: pa.Field) -> str:
    fmt = (field.metadata or {}).get(FORMAT_KEY)
    base = str(field.type)
    return f"{base} (`{fmt.decode()}`)" if fmt else base


EXTRAS_TEXT = "Upstream fields without a typed column, as JSON (schema-drift safety net)."
TODO = "TODO"


@dataclass(frozen=True)
class Described:
    """One column description with its provenance."""

    text: str
    source: str | None = None
    authored: bool = False


def _entry(value: Any) -> Described:
    if isinstance(value, str):
        return Described(value, None, True)
    return Described(str(value["text"]), value.get("source"), bool(value.get("authored", False)))


def load_descriptions(
    docs_dir: Path, source: str
) -> tuple[dict[str, str], dict[str, dict[str, Described]]]:
    """``(sources, {dataset or "*": {column: Described}})`` of ``docs/columns/<source>.json``."""
    path = docs_dir / "columns" / f"{source}.json"
    if not path.exists():
        return {}, {}
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    sources = {str(k): str(v) for k, v in data.pop("_sources", {}).items()}
    table = {
        dataset: {col: _entry(v) for col, v in columns.items()} for dataset, columns in data.items()
    }
    return sources, table


def lookup(
    table: Mapping[str, Mapping[str, Described]], dataset: str, column: str
) -> Described | None:
    """Dataset-specific description, else the source-wide ``"*"`` default, else ``None``."""
    if column == "_extras":
        return Described(EXTRAS_TEXT, None, True)
    return table.get(dataset, {}).get(column) or table.get("*", {}).get(column)


def description_coverage(docs_dir: Path) -> dict[str, tuple[int, int]]:
    """``{source: (described columns, total columns)}`` over every registered dataset."""
    catalog.register_all()
    out: dict[str, list[int]] = {}
    tables: dict[str, dict[str, dict[str, Described]]] = {}
    for spec in DATASETS.values():
        if spec.source not in tables:
            tables[spec.source] = load_descriptions(docs_dir, spec.source)[1]
        counts = out.setdefault(spec.source, [0, 0])
        for field in spec.schema:
            counts[1] += 1
            counts[0] += lookup(tables[spec.source], spec.name, field.name) is not None
    return {k: (v[0], v[1]) for k, v in out.items()}


def _cell(found: Described | None) -> str:
    if found is None:
        return TODO
    tag = f" (src: {found.source})" if found.source else (" (authored)" if found.authored else "")
    return found.text.replace("|", "/") + tag


def render_dataset(
    spec: DatasetSpec, table: Mapping[str, Mapping[str, Described]] | None = None
) -> str:
    """Markdown block (with markers) documenting one dataset."""
    notes = table or {}
    key = f"{spec.source}.{spec.name}"
    partition = "Hive `season=YYYY`" if spec.partition == "season" else "none (flat)"
    lines = [
        f"<!-- BEGIN GENERATED:{key} -->",
        f"### Dataset: {spec.name}",
        "",
        spec.description,
        "",
        f"- **View:** `{spec.view}`",
        f"- **Processed path:** `processed/{spec.source}/{spec.name}/"
        + ("season=YYYY/" if spec.partition == "season" else "")
        + "part-<chunk>.parquet`",
        f"- **Partitioning:** {partition}",
        f"- **Key:** {', '.join(f'`{k}`' for k in spec.keys)}",
        "",
        "| Column | Type | Nullable | Upstream name | Description |",
        "| --- | --- | --- | --- | --- |",
    ]
    for field in spec.schema:
        meta = field.metadata or {}
        upstream = meta.get(UPSTREAM_KEY, b"").decode() or "—"
        lines.append(
            f"| `{field.name}` | {_type_name(field)} | {'yes' if field.nullable else 'no'} | "
            f"{upstream if upstream == '—' else '`' + upstream + '`'} | "
            f"{_cell(lookup(notes, spec.name, field.name))} |"
        )
    lines += ["", f"<!-- END GENERATED:{key} -->", ""]
    return "\n".join(lines)


def render_source_doc(current: str, specs: Iterable[DatasetSpec], docs_dir: Path) -> str:
    """Return ``current`` with every dataset block replaced (or appended under the heading)."""
    text = current
    missing: list[str] = []
    for spec in specs:
        block = render_dataset(spec, load_descriptions(docs_dir, spec.source)[1])
        key = f"{spec.source}.{spec.name}"
        pattern = re.compile(
            rf"<!-- BEGIN GENERATED:{re.escape(key)} -->.*?<!-- END GENERATED:{re.escape(key)} -->\n?",
            re.DOTALL,
        )
        if (found := pattern.search(text)) is not None:
            text = text[: found.start()] + block + text[found.end() :]
        else:
            missing.append(block)
    if missing:
        if HEADING not in text:
            text = text.rstrip("\n") + f"\n\n{HEADING}\n\n"
        text = text.rstrip("\n") + "\n\n" + "\n".join(missing)
    return text if text.endswith("\n") else text + "\n"


def render_sources_block(source: str, sources: Mapping[str, str]) -> str:
    """Generated list of the description sources cited by ``source``'s dictionaries."""
    key = f"{source}.description_sources"
    lines = [f"<!-- BEGIN GENERATED:{key} -->", "### Description sources", ""]
    if sources:
        lines += [f"- `{name}`: {where}" for name, where in sorted(sources.items())]
    else:
        lines.append("No column descriptions have been written for this source yet.")
    lines += ["", f"<!-- END GENERATED:{key} -->", ""]
    return "\n".join(lines)


def _with_sources_block(text: str, source: str, sources: Mapping[str, str]) -> str:
    block = render_sources_block(source, sources)
    key = f"{source}.description_sources"
    pattern = re.compile(
        rf"<!-- BEGIN GENERATED:{re.escape(key)} -->.*?<!-- END GENERATED:{re.escape(key)} -->\n?",
        re.DOTALL,
    )
    if (found := pattern.search(text)) is not None:
        return text[: found.start()] + block + text[found.end() :]
    if HEADING in text:
        head, tail = text.split(HEADING, 1)
        return f"{head}{HEADING}\n\n{block}\n{tail.lstrip(chr(10))}"
    return text.rstrip("\n") + f"\n\n{HEADING}\n\n{block}"


def stale_blocks(text: str, specs: Iterable[DatasetSpec]) -> list[str]:
    """Keys of datasets that have no generated block in ``text``."""
    present = {m.group("key") for m in _BLOCK.finditer(text)}
    return [s.key for s in specs if s.key not in present]


def generate_docs(docs_dir: Path, *, write: bool = True) -> dict[str, bool]:
    """Regenerate ``docs/sources/<source>.md``; returns ``{file: changed}``.

    With ``write=False`` nothing is written (used by ``docs generate --check`` and the tests).
    """
    catalog.register_all()
    by_source: dict[str, list[DatasetSpec]] = {}
    for spec in DATASETS.values():
        by_source.setdefault(spec.source, []).append(spec)
    changed: dict[str, bool] = {}
    for source, specs in sorted(by_source.items()):
        path = docs_dir / "sources" / f"{source}.md"
        current = path.read_text(encoding="utf-8") if path.exists() else f"# {source}\n"
        new = render_source_doc(current, sorted(specs, key=lambda s: s.name), docs_dir)
        new = _with_sources_block(new, source, load_descriptions(docs_dir, source)[0])
        changed[str(path)] = new != current
        if write and new != current:
            path.write_text(new, encoding="utf-8")
    return changed
