"""Measure the typical size of every registered dataset in a lake and write ``typical_sizes.json``.

``baseballpy ingest --dry-run`` reads that table to say what a command would download
(``src/baseballpy/ingest/estimate.py``). The values are measured, never guessed: for a dataset split by
season, the median bytes of one season folder; for any other dataset, the bytes of its folder. A dataset the
lake does not hold is left out, and the dry run then counts it as unknown.

    uv run python scripts/measure_dataset_sizes.py [--home PATH] [--out PATH]
"""

import argparse
import json
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS
from baseballpy.core.listing import is_hidden
from baseballpy.sources import catalog

DEFAULT_OUT = (
    Path(__file__).resolve().parent.parent / "src" / "baseballpy" / "core" / "typical_sizes.json"
)


def measure(config: LakeConfig) -> dict[str, dict[str, int]]:
    """``dataset key -> {bytes_per_folder, folders_measured}`` for the datasets this lake holds."""
    catalog.register_all()
    measured: dict[str, dict[str, int]] = {}
    for spec in sorted(DATASETS.values(), key=lambda s: s.key):
        root = config.processed_dir(spec.source, spec.name)
        if not root.is_dir():
            continue
        folders: dict[str, int] = defaultdict(int)
        for path in root.rglob("*.parquet"):
            if is_hidden(path, root):
                continue
            relative = path.relative_to(root).parts
            folder = relative[0] if spec.partition == "season" and len(relative) > 1 else ""
            folders[folder] += path.stat().st_size
        if not folders:
            continue
        measured[spec.key] = {
            "bytes_per_folder": int(statistics.median(folders.values())),
            "folders_measured": len(folders),
        }
    return measured


def main() -> None:
    """Measure the lake and write the table."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--home", type=Path, default=None, help="lake home (default: the configured one)"
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    config = LakeConfig(home=args.home) if args.home else LakeConfig()
    datasets = measure(config)
    payload = {
        "measured_on": datetime.now(UTC).date().isoformat(),
        "what": "median bytes of one season folder (or the whole folder for datasets without seasons)",
        "datasets": datasets,
    }
    args.out.write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"wrote {len(datasets)} dataset sizes to {args.out}")


if __name__ == "__main__":
    main()
