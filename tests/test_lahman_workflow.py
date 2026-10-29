"""Lahman: fingerprints, both cache tiers on is_current(), documents, imports, access, names."""

import io
import zipfile
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pytest
import respx

from baseballpy.cache_check import CURRENT, NOT_CHECKED, check_raw
from baseballpy.core import sources_lock
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import datasets_for
from baseballpy.core.upstream import CONTENT_SHA256, GIT_BLOB, stored_fingerprint
from baseballpy.ingest.types import Selection, make_job
from baseballpy.sources import catalog, lahman
from baseballpy.sources.lahman.adapter import LahmanAdapter
from baseballpy.sources.lahman.api import LahmanSource
from baseballpy.sources.lahman.extractor import DOCUMENT_DATASET, LOCAL_IMPORT
from baseballpy.sources.lahman.schema import LahmanTable, canonical_table_name

BATTING_V1 = (
    "playerID,yearID,stint,teamID,lgID,G,AB,R,H,2B,3B,HR,RBI,SB,CS,BB,SO,IBB,HBP,SH,SF,GIDP\n"
    "ohtansh01,2024,1,LAD,NL,159,636,134,197,38,7,54,130,59,4,81,162,20,6,0,5,5\n"
    "judgaa01,2024,1,NYA,AL,158,559,122,180,36,1,58,144,10,0,133,171,20,9,0,4,22\n"
)
BATTING_V2 = BATTING_V1 + "troutmi01,2024,1,LAA,AL,29,100,20,30,5,0,10,25,1,0,10,25,1,1,0,1,2\n"
PEOPLE = (
    "playerID,birthYear,nameFirst,nameLast,bbrefID,retroID\n"
    "ohtansh01,1994,Shohei,Ohtani,ohtansh01,ohtas001\n"
)
DOCS = {
    "README.md": b"# mirror",
    "LICENSE": b"Creative Commons Attribution-ShareAlike 3.0",
    "data/readme2025.txt": b"The SABR Lahman Baseball Database 1871-2025",
}


class LahmanRepo:
    """A fake mirror at one ref: serves its git tree and files through respx."""

    def __init__(self, files: dict[str, tuple[bytes, str]], ref: str | None = None) -> None:
        self.files = files
        base = sources_lock.get_source_ref("lahman")
        self.ref = ref or base.ref
        self.repo = base.repo

    def mount(self) -> None:
        tree = [
            {"path": p, "type": "blob", "size": len(c), "sha": sha}
            for p, (c, sha) in self.files.items()
        ]
        respx.get(
            f"https://api.github.com/repos/{self.repo}/git/trees/{self.ref}?recursive=1"
        ).mock(return_value=httpx.Response(200, json={"truncated": False, "tree": tree}))
        for path, (content, _) in self.files.items():
            url = f"https://raw.githubusercontent.com/{self.repo}/{self.ref}/{path}"
            respx.get(url).mock(return_value=httpx.Response(200, content=content))

    def raw_calls(self) -> int:
        return sum(1 for c in respx.calls if "raw.githubusercontent.com" in str(c.request.url))


def _repo(
    batting: str = BATTING_V1, sha: str = "blob-batting-1", ref: str | None = None
) -> LahmanRepo:
    files = {
        "data/Batting.csv": (batting.encode(), sha),
        "data/People.csv": (PEOPLE.encode(), "blob-people"),
    }
    files.update({path: (content, f"blob-{path}") for path, content in DOCS.items()})
    return LahmanRepo(files, ref)


@respx.mock
def test_fingerprints_one_entry_per_file_and_documents_are_kept(tmp_path: Path) -> None:
    repo = _repo()
    repo.mount()
    cfg = LakeConfig(home=tmp_path)
    source = LahmanSource(cfg)
    assert len(source.batting()) == 2

    chunks = source.extractor.manifest_for("Batting").chunks()
    assert list(chunks) == ["Batting.csv"]  # exactly one entry per raw file
    entry = chunks["Batting.csv"]
    assert entry["records_count"] == 2 and entry["source_ref"] == repo.ref
    assert entry["origin"] == f"{repo.repo}@{repo.ref}"
    fingerprint = stored_fingerprint(entry)
    assert fingerprint is not None and fingerprint.kind == GIT_BLOB
    assert fingerprint.value == "blob-batting-1" and fingerprint.origin.endswith(
        ":data/Batting.csv"
    )
    # the processed Parquet remembers which raw file it was built from
    processed = cfg.dataset_manifest("lahman", "Batting").get_chunk("data")
    assert stored_fingerprint(processed) == fingerprint

    # README, licence and the data dictionary are kept with hashes
    documents = cfg.raw_dir("lahman", DOCUMENT_DATASET)
    assert sorted(p.name for p in documents.iterdir() if p.name != "manifest.json") == [
        "LICENSE",
        "README.md",
        "readme2025.txt",
    ]
    assert source.raw.verify("lahman", DOCUMENT_DATASET, "LICENSE")
    licence = cfg.dataset_manifest("lahman", DOCUMENT_DATASET, "raw").chunks()["LICENSE"]
    assert stored_fingerprint(licence).value == "blob-LICENSE"  # type: ignore[union-attr]


@respx.mock
def test_a_second_process_serves_both_tiers_without_any_request(tmp_path: Path) -> None:
    repo = _repo()
    repo.mount()
    LahmanSource(LakeConfig(home=tmp_path)).batting()
    calls = len(respx.calls)
    again = LahmanSource(LakeConfig(home=tmp_path))  # empty memory: tiers are really checked
    loaded = again.load_table("Batting")
    assert loaded.from_cache and len(loaded.table) == 2
    assert len(respx.calls) == calls  # the pinned tree listing is cached on disk, nothing fetched


@respx.mock
def test_moving_the_pin_refetches_the_raw_file_and_rebuilds_the_parquet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo().mount()
    LahmanSource(LakeConfig(home=tmp_path)).batting()
    new_ref = "b" * 40
    monkeypatch.setenv("BASEBALLPY_LAHMAN_REF", new_ref)
    _repo(BATTING_V2, "blob-batting-2", ref=new_ref).mount()
    source = LahmanSource(LakeConfig(home=tmp_path))
    loaded = source.load_table("Batting")
    assert not loaded.from_cache and len(loaded.table) == 3  # raw AND processed were replaced
    entry = source.extractor.file_entry("Batting")
    assert entry is not None and stored_fingerprint(entry).value == "blob-batting-2"  # type: ignore[union-attr]
    assert len(LahmanSource(LakeConfig(home=tmp_path)).batting()) == 3


@respx.mock
def test_an_unchanged_blob_under_a_new_pin_is_not_downloaded_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo().mount()
    LahmanSource(LakeConfig(home=tmp_path)).batting()
    monkeypatch.setenv("BASEBALLPY_LAHMAN_REF", "c" * 40)
    same = _repo(ref="c" * 40)  # new commit, same blob SHAs: the file did not change
    same.mount()
    before = same.raw_calls()
    assert LahmanSource(LakeConfig(home=tmp_path)).load_table("Batting").from_cache
    assert same.raw_calls() == before


@respx.mock
def test_offline_without_a_cached_listing_the_pinned_commit_decides(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    repo = _repo()
    repo.mount()
    cfg = LakeConfig(home=tmp_path)
    LahmanSource(cfg).batting()
    for listing in (cfg.http_cache_root / "github-tree").glob("*.json"):
        listing.unlink()  # the tree was never saved
    respx.get(f"https://api.github.com/repos/{repo.repo}/git/trees/{repo.ref}?recursive=1").mock(
        return_value=httpx.Response(500)
    )
    raw_before = repo.raw_calls()
    with caplog.at_level("WARNING"):
        loaded = LahmanSource(cfg).load_table("Batting")
    assert loaded.from_cache and repo.raw_calls() == raw_before
    assert "could not list" in caplog.text


@respx.mock
def test_tables_are_remembered_in_process_and_noticed_when_the_parquet_changes(
    tmp_path: Path,
) -> None:
    _repo().mount()
    cfg = LakeConfig(home=tmp_path)
    first = LahmanSource(cfg)
    table = first.batting()
    assert first.get_table("batting") is table  # any letter case, same object, no work
    other = LahmanSource(cfg)
    other.get_table("Batting", refresh=True)  # rewrites the Parquet
    assert first.batting() is not table  # the stamp changed, so it is read again
    first.clear_cache()
    assert first.batting() is not table


def test_table_names_ignore_letter_case_and_unknown_names_list_the_27() -> None:
    assert canonical_table_name("batting") == "Batting"
    assert canonical_table_name(" HALLOFFAME ") == "HallOfFame"
    assert canonical_table_name(LahmanTable.PEOPLE) == "People"
    with pytest.raises(ValueError, match=r"unknown table 'nope'.*AllstarFull.*TeamsHalf"):
        canonical_table_name("nope")


def test_enum_registry_and_generated_tables_name_the_same_27_tables() -> None:
    from baseballpy.sources.lahman.tables import LAHMAN_COLUMNS, LAHMAN_KEYS

    catalog.register_all()
    registry = {d.name for d in datasets_for("lahman")}
    enum = {t.value for t in LahmanTable}
    assert len(enum) == 27 and registry == enum == set(LAHMAN_COLUMNS) == set(LAHMAN_KEYS)


@respx.mock
def test_generic_top_level_accessor_serves_every_table(tmp_path: Path) -> None:
    _repo().mount()
    lahman.get_default_source.reset()
    try:
        assert lahman.tables() == [t.value for t in LahmanTable]
        assert lahman.table("PEOPLE").num_rows == 1
        assert lahman.table("batting").num_rows == 2
        with pytest.raises(ValueError, match="unknown table"):
            lahman.table("nope")
    finally:
        lahman.get_default_source.reset()


@respx.mock
def test_ingest_jobs_report_cache_hits(tmp_path: Path) -> None:
    _repo().mount()
    adapter = LahmanAdapter()
    job = make_job("lahman", "table", name="batting")  # lower case is accepted
    first = adapter.run(job)
    second = adapter.run(job)
    assert first.rows == second.rows == 2
    assert not first.cache_hit and second.cache_hit
    planned = adapter.plan(Selection(datasets=("batting", "PEOPLE")))
    assert [j.param("name") for j in planned] == ["Batting", "People"]


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_import_keeps_documents_and_unknown_csvs_raw_only_and_ignores_the_rest(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cfg = LakeConfig(home=tmp_path / "lake")
    archive = tmp_path / "release.zip"
    archive.write_bytes(
        _zip(
            {
                "lahman/People.csv": PEOPLE.encode(),
                "lahman/Batting.csv": BATTING_V1.encode(),
                "lahman/readme2025.txt": b"dictionary",
                "lahman/LICENSE": b"licence",
                "lahman/Extra.csv": b"a,b\n1,2\n",
                "lahman/lahman.mdb": b"binary",
                "__MACOSX/People.csv": b"junk",
            }
        )
    )
    source = LahmanSource(cfg)
    with caplog.at_level("WARNING"):
        assert source.import_archive(archive) == 2
    report = source.last_import
    assert sorted(report.tables) == ["Batting", "People"]
    assert sorted(report.documents) == ["LICENSE", "readme2025.txt"]
    assert report.raw_only == ["Extra"]
    assert "not one of the 27 Lahman tables" in caplog.text
    # the unknown CSV is kept as bytes but is never a table
    assert (cfg.raw_dir("lahman", "Extra") / "Extra.csv").read_bytes() == b"a,b\n1,2\n"
    assert not cfg.processed_dir("lahman", "Extra").exists()
    assert source.raw.get("lahman", DOCUMENT_DATASET, "LICENSE") == b"licence"
    # supplied data: one entry per file, content fingerprint, authoritative, served without network
    entry = source.extractor.file_entry("Batting")
    assert entry is not None and entry["source_ref"] == LOCAL_IMPORT
    assert stored_fingerprint(entry).kind == CONTENT_SHA256  # type: ignore[union-attr]
    assert source.extractor.is_local("Batting")
    assert LahmanSource(cfg).load_table("Batting").from_cache


@respx.mock
def test_mixing_a_supplied_table_with_a_mirror_table_warns_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cfg = LakeConfig(home=tmp_path / "lake")
    archive = tmp_path / "partial.zip"
    archive.write_bytes(_zip({"People.csv": PEOPLE.encode()}))  # a partial supplied release
    _repo().mount()
    source = LahmanSource(cfg)
    source.import_archive(archive)
    with caplog.at_level("WARNING"):
        source.batting()
    assert caplog.text.count("mixed Lahman release") == 1
    assert "People" in caplog.text


@respx.mock
def test_cache_check_compares_mirror_files_and_leaves_supplied_files_unchecked(
    tmp_path: Path,
) -> None:
    repo = _repo()
    repo.mount()
    cfg = LakeConfig(home=tmp_path)
    source = LahmanSource(cfg)
    source.batting()
    archive = tmp_path / "p.zip"
    archive.write_bytes(
        _zip({"Salaries.csv": b"yearID,teamID,lgID,playerID,salary\n2020,BOS,AL,a01,100\n"})
    )
    source.import_archive(archive)
    latest: dict[str, Any] = {f"data/{n}.csv": sha for n, sha in (("Batting", "blob-batting-1"),)}
    results = {
        r.name: r.upstream
        for r in check_raw(cfg, sources=["lahman"], upstream=True, latest=lambda repo_name: latest)
    }
    assert results["Batting.csv"] == CURRENT
    assert results["Salaries.csv"] == NOT_CHECKED  # supplied: there is no upstream to compare with
    assert results["LICENSE"] == "removed"  # not in the fake latest listing, still reported


# -- data quality: relationships between tables, in any load order ----------------------------------

BATTING_ROWS = (
    "playerID,yearID,stint,teamID,lgID,G\n"
    "known01,2025,1,BOS,AL,10\n"
    "ghost01,2025,1,BOS,AL,10\n"
    "known01,2024,1,ZZZ,AL,10\n"
)


def _csv(header: str, *rows: str) -> bytes:
    return (header + "\n" + "\n".join(rows) + "\n").encode()


def test_findings_do_not_depend_on_the_order_tables_are_stored_in(tmp_path: Path) -> None:
    cfg = LakeConfig(home=tmp_path)
    source = LahmanSource(cfg)
    source._import_csv("Batting.csv", BATTING_ROWS.encode())  # stored BEFORE its parents exist
    manifest = cfg.dataset_manifest("lahman", "Batting")
    assert "quality" not in (manifest.get_chunk("data") or {})  # nothing to compare with yet

    source._import_csv("People.csv", _csv("playerID", "known01"))
    quality = manifest.get_chunk("data")["quality"]  # type: ignore[index]
    assert quality == {"orphan_rows:playerID->People": 1}

    source._import_csv("Teams.csv", _csv("yearID,teamID,lgID", "2025,BOS,AL"))
    quality = manifest.get_chunk("data")["quality"]  # type: ignore[index]
    assert quality == {"orphan_rows:playerID->People": 1, "orphan_rows:yearID+teamID->Teams": 1}

    source._import_csv("People.csv", _csv("playerID", "known01", "ghost01"))  # the parent grows
    assert manifest.get_chunk("data")["quality"] == {"orphan_rows:yearID+teamID->Teams": 1}  # type: ignore[index]
    source._import_csv("Teams.csv", _csv("yearID,teamID,lgID", "2025,BOS,AL", "2024,ZZZ,AL"))
    assert "quality" not in manifest.get_chunk("data")  # type: ignore[operator]


def test_empty_ids_are_not_orphans_and_other_relationships_are_checked(tmp_path: Path) -> None:
    from baseballpy.sources.lahman import quality

    child = pa.table({"schoolID": ["a", None, "zzz"]})
    parent = pa.table({"schoolID": ["a", "b"]})
    assert quality.orphan_rows(child, ("schoolID",), parent, ("schoolID",)) == 1
    findings = quality.foreign_key_findings(
        "CollegePlaying", child, lambda name: parent if name == "Schools" else None
    )
    assert findings == {"orphan_rows:schoolID->Schools": 1}
    assert quality.foreign_key_findings("Parks", child, lambda _: parent) == {}  # not a child


def test_catalog_status_shows_the_findings(tmp_path: Path) -> None:
    import json

    from click.testing import CliRunner

    from baseballpy.cli import main
    from baseballpy.cli_ingest import scan_lake

    source = LahmanSource(LakeConfig())
    source._import_csv("People.csv", _csv("playerID", "known01"))
    source._import_csv("Batting.csv", BATTING_ROWS.encode())
    status = {s.dataset: s for s in scan_lake(LakeConfig())}
    assert status["Batting"].quality == {"orphan_rows:playerID->People": 1}
    assert status["People"].quality == {}
    out = CliRunner().invoke(main, ["catalog", "status", "--source", "lahman", "--json"])
    rows = {r["dataset"]: r for r in map(json.loads, out.output.splitlines()) if "dataset" in r}
    assert rows["Batting"]["quality"] == {"orphan_rows:playerID->People": 1}
    table = CliRunner().invoke(main, ["catalog", "status", "--source", "lahman"])
    assert "data quality lahman.Batting: orphan_rows:playerID->People=1" in " ".join(
        table.output.split()
    )
