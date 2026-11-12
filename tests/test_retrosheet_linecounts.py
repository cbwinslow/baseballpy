"""Row counts of the event-derived tables against the lines of the raw event files (change data-validation-roundtrip).

Event files are not CSV, so the cell check cannot read them; counting is the cheapest proof that no play or substitution
was lost or invented: ``events`` has one row per ``play`` line whose event is not ``NP``, ``events_postseason`` the same
for the postseason files, ``substitutions`` one row per ``sub`` line (verified on 2023: 190,416, 3,263 and 27,444).
"""

from pathlib import Path

import pyarrow as pa
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.roundtrip import roundtrip_dataset
from baseballpy.core.stores import ProcessedStore, RawStore
from baseballpy.sources import catalog
from baseballpy.sources.adapters import register_all_adapters

EVA = (
    'id,AAA202304010\nversion,2\ninfo,visteam,BBB\nstart,aaaa001,"A",0,1,8\n'
    'play,1,0,aaaa001,00,X,S8\nplay,1,0,aaaa002,00,X,NP\nsub,aaaa003,"C",0,2,4\nplay,1,1,bbbb001,00,X,K\n'
    "data,er,aaaa001,0\n"
)
EVE = "id,AAA202310010\nplay,1,0,aaaa001,00,X,S8\nplay,1,0,aaaa002,00,X,NP\n"


def _lake(tmp_path: Path, events_rows: int, post_rows: int, sub_rows: int) -> LakeConfig:
    catalog.register_all()
    register_all_adapters()
    config = LakeConfig(home=tmp_path)
    raw = RawStore(config)
    raw.put("retrosheet", "event_files", "2023AAA.EVA", EVA.encode(), season=2023)
    raw.put("retrosheet", "event_files", "2023ALCS.EVE", EVE.encode(), season=2023)
    for name, rows in (
        ("events", events_rows),
        ("events_postseason", post_rows),
        ("substitutions", sub_rows),
    ):
        spec = get_dataset("retrosheet", name)
        table = pa.Table.from_pylist([{}] * rows, schema=spec.schema)
        ProcessedStore(config).put(spec, table, chunk_id="events_2023", season=2023)
    return config


@pytest.mark.parametrize(
    ("dataset", "expected"), [("events", 2), ("events_postseason", 1), ("substitutions", 1)]
)
def test_matching_counts_are_ok_and_say_they_are_counts_only(
    tmp_path: Path, dataset: str, expected: int
) -> None:
    config = _lake(tmp_path, events_rows=2, post_rows=1, sub_rows=1)
    check = roundtrip_dataset(config, get_dataset("retrosheet", dataset))
    assert check.status == "ok", check
    assert check.raw_rows == expected and check.compared == expected
    assert any("counts only" in note for note in check.notes), check.notes


def test_a_lost_or_an_invented_row_is_found_by_the_count(tmp_path: Path) -> None:
    config = _lake(tmp_path, events_rows=1, post_rows=2, sub_rows=1)  # one play lost, one invented
    lost = roundtrip_dataset(config, get_dataset("retrosheet", "events"))
    assert lost.status == "loss" and [(x.kind, x.count) for x in lost.losses] == [
        ("row_missing", 1)
    ]
    invented = roundtrip_dataset(config, get_dataset("retrosheet", "events_postseason"))
    assert invented.status == "loss" and [(x.kind, x.count) for x in invented.losses] == [
        ("row_extra", 1)
    ]
