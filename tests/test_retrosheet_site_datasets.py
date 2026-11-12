"""Phase 1 of the Retrosheet site datasets (change retrosheet-site-datasets): transactions and the *0 biography tables.

They live in ``raw/retrosheet/site_files/`` as the site's zips; ``baseballpy ingest retrosheet -d site_*`` parses them
into typed Parquet. They are opt-in: a default Retrosheet ingest never contacts retrosheet.org.
"""

import io
import zipfile
from pathlib import Path

import pyarrow as pa
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.stores import RawStore
from baseballpy.ingest.types import Selection
from baseballpy.sources import catalog
from baseballpy.sources.retrosheet import site
from baseballpy.sources.retrosheet.adapter import RetrosheetAdapter

NAMES = (
    "transactions",
    "managers0",
    "umpires0",
    "coaches0",
    "ballparks0",
    "teams0",
)

TRAN = (
    '"20030603",,,"20030629",,1,"aardd001","Da","","","SFN","NL",,1,22,\n'
    '"19841104",,,,,7,"aased001","Fg","CAL","AL","","",,,,\n'
    '"19520000",,@,,,8,"aaroh101","Fo","","","BSN","NL",,,,info text\n'
)
MANAGERS = "id,lastname,firstname,first_g,last_g\nabbob101,Abbott,Bob,19300401,19311001\n"
UMPIRES = "id,lastname,firstname,first_g,last_g\nabbed901,Abbott,Ed,18770501,18770930\n"
COACHES = "id,year,team,role,first_g,last_g\naaroh101,1990,ATL,C,19900409,19901003\n"
BALLPARKS = (
    "site,name,city,state,first_g,last_g\nALB01,Riverside Park,Albany,NY,18800101,18821001\n"
)
TEAMS = "team,city,nickname,first_g,last_g\nALB,Albany,Grays,18800101,18821001\n"


def _zip(members: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, text in members.items():
            zf.writestr(name, text)
    return buffer.getvalue()


def _store_site_zips(home: Path) -> LakeConfig:
    config = LakeConfig(home=home)
    raw = RawStore(config)
    files = {
        "tranDB.zip": {"tran.txt": TRAN, "readme.txt": "x"},
        "biodata.zip": {
            "managers0.csv": MANAGERS,
            "umpires0.csv": UMPIRES,
            "coaches0.csv": COACHES,
            "ballparks0.csv": BALLPARKS,
            "teams0.csv": TEAMS,
        },
    }
    for name, members in files.items():
        data = _zip(members)
        staging = raw.path_for("retrosheet", site.RAW_DATASET, name).with_name(name + ".download")
        staging.parent.mkdir(parents=True, exist_ok=True)
        staging.write_bytes(data)
        import hashlib

        raw.adopt(
            "retrosheet",
            site.RAW_DATASET,
            name,
            staging,
            sha256=hashlib.sha256(data).hexdigest(),
            size=len(data),
        )
    return config


def test_the_six_site_datasets_are_registered_opt_in_and_strict() -> None:
    catalog.register_all()
    for name in NAMES:
        spec = get_dataset("retrosheet", name)
        assert spec.ingest == "opt_in", f"{name} must not download by default"
        assert spec.view == f"retrosheet_{name}"
        assert len(spec.schema) >= 5
        assert spec.keys and all(k in spec.schema.names for k in spec.keys), name
    assert set(NAMES) <= set(site.SITE_DATASETS)


def test_a_default_ingest_never_plans_a_site_job_but_a_site_dataset_does() -> None:
    adapter = RetrosheetAdapter(source=object())
    default_jobs = adapter.plan(Selection(seasons=(2024,)))
    assert all(job.task != "site" for job in default_jobs)
    named = adapter.plan(Selection(datasets=("transactions", "managers0")))
    assert [job.task for job in named] == ["site"]
    assert named[0].param("datasets") == "transactions,managers0"


def test_stored_zips_become_typed_tables_without_any_request(tmp_path: Path) -> None:
    """The network is blocked in tests: nothing may be requested when the zips are already stored."""
    config = _store_site_zips(tmp_path)
    tables = site.read_site_datasets(config, NAMES)
    assert set(tables) == set(NAMES)
    tran = tables["transactions"]
    assert tran.num_rows == 3
    assert tran.schema.field("transaction_id").type == pa.int32()
    assert tran.schema.field("draft_round").type in (pa.int16(), pa.int32())
    assert tran.column("player").to_pylist() == ["aardd001", "aased001", "aaroh101"]
    assert tran.column("primary_date").to_pylist()[2] == "19520000", (
        "partial dates stay text, never invented"
    )
    assert tran.column("info").to_pylist()[2] == "info text"
    managers = tables["managers0"]
    assert managers.column("manager_id").to_pylist() == ["abbob101"]
    assert str(managers.schema.field("first_g").type) == "date32[day]"


def test_a_missing_zip_is_reported_not_guessed(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    with pytest.raises(FileNotFoundError, match="tranDB.zip"):
        site.read_site_datasets(config, ("transactions",))


def test_the_site_unit_fetches_only_what_is_missing() -> None:
    needed = site.files_for(("transactions", "managers0", "teams0"))
    assert [f.name for f in needed] == ["tranDB.zip", "biodata.zip"]
    assert all(f.group == "core" for f in needed)


def test_ingest_site_writes_typed_parquet_then_skips_a_current_dataset(tmp_path: Path) -> None:
    """Zips already stored: no request (the network is blocked); the second run finds every dataset current."""
    from baseballpy.sources.retrosheet.api import RetrosheetSource

    config = _store_site_zips(tmp_path)
    source = RetrosheetSource(config)
    first = source.ingest_site(NAMES)
    assert first == {
        "transactions": 3,
        "managers0": 1,
        "umpires0": 1,
        "coaches0": 1,
        "ballparks0": 1,
        "teams0": 1,
    }
    stored = source.store.read_part(get_dataset("retrosheet", "transactions"), "data", None)
    assert stored.schema == get_dataset("retrosheet", "transactions").schema
    assert source.ingest_site(NAMES) == dict.fromkeys(first)


def test_a_site_dataset_the_registry_does_not_know_is_refused(tmp_path: Path) -> None:
    from baseballpy.sources.retrosheet.api import RetrosheetSource

    with pytest.raises(ValueError, match="unknown site dataset"):
        RetrosheetSource(LakeConfig(home=tmp_path)).ingest_site(["site_nope"])
