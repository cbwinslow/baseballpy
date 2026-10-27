"""Generate the per-dataset column dictionaries in ``docs/sources/<source>.md`` from the registry.

For every registered dataset a block delimited by ``<!-- BEGIN GENERATED:<source>.<dataset> -->`` /
``<!-- END GENERATED:... -->`` is rendered (view, partitioning, key, column | type | nullable |
upstream name | description). Descriptions are hand-curated in ``docs/columns/<source>.json``
(``{"<dataset>": {"<column>": "text"}}``). A test regenerates and fails when the committed docs
are stale, so documentation cannot drift from the schemas.
"""

import json
import re
from collections.abc import Iterable
from pathlib import Path

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


def _descriptions(docs_dir: Path, source: str) -> dict[str, dict[str, str]]:
    path = docs_dir / "columns" / f"{source}.json"
    if not path.exists():
        return {}
    data: dict[str, dict[str, str]] = json.loads(path.read_text(encoding="utf-8"))
    return data


def render_dataset(spec: DatasetSpec, descriptions: dict[str, str] | None = None) -> str:
    """Markdown block (with markers) documenting one dataset."""
    notes = descriptions or {}
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
            f"{notes.get(field.name, '').replace('|', '/')} |"
        )
    lines += ["", f"<!-- END GENERATED:{key} -->", ""]
    return "\n".join(lines)


def render_source_doc(current: str, specs: Iterable[DatasetSpec], docs_dir: Path) -> str:
    """Return ``current`` with every dataset block replaced (or appended under the heading)."""
    text = current
    missing: list[str] = []
    for spec in specs:
        block = render_dataset(spec, _descriptions(docs_dir, spec.source).get(spec.name))
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
        changed[str(path)] = new != current
        if write and new != current:
            path.write_text(new, encoding="utf-8")
    return changed
