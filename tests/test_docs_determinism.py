"""Every source page states what is pinned, what is live and what varies (B-412, AGENTS.md section 15)."""

from pathlib import Path

from baseballpy.core.datasets import DATASETS
from baseballpy.sources import catalog

HEADING = "## Determinism: what is pinned, what is live, what varies"
LABELS = (
    "**Pinned:**",
    "**Live (cannot be pinned):**",
    "**Kept, so a rebuild is identical:**",
    "**What varies between runs:**",
    "**Proof:**",
)


def test_every_source_page_has_the_determinism_section_with_all_five_answers() -> None:
    catalog.register_all()
    docs = Path(__file__).parent.parent / "docs" / "sources"
    for source in sorted({spec.source for spec in DATASETS.values()}):
        text = (docs / f"{source}.md").read_text(encoding="utf-8")
        assert HEADING in text, f"{source}.md has no determinism section"
        section = text.split(HEADING, 1)[1].split("\n## ", 1)[0]
        missing = [label for label in LABELS if label not in section]
        assert not missing, f"{source}.md determinism section lacks {missing}"
