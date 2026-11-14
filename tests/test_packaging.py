"""The source archive leaves out local scratch folders (they once made it 4 times larger)."""

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def test_sdist_excludes_local_scratch_and_reference_folders() -> None:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    excluded = config["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"]
    for folder in (".delta", ".claude", ".baseballpy", "docs/references"):
        assert folder in excluded, f"{folder} would be packed into the sdist"
