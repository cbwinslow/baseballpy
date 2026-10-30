"""Every Retrosheet operation that downloads, parses or stores data is audit-logged and timed."""

from pathlib import Path

import pytest
import respx
from conftest import RetroRepo
from test_retrosheet_coverage import full_season

from baseballpy.core.audit import AuditConfig, AuditLogger
from baseballpy.core.config import LakeConfig
from baseballpy.sources.retrosheet import api, downloader
from baseballpy.sources.retrosheet.api import RetrosheetSource


@respx.mock
def test_a_season_and_the_reference_ingest_leave_an_audit_trail(
    tmp_path: Path, retro_repo: RetroRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit = AuditLogger(AuditConfig(base_dir=tmp_path / "audit"))
    monkeypatch.setattr(api, "default_audit_logger", audit)
    monkeypatch.setattr(downloader, "default_audit_logger", audit)
    full_season(retro_repo).mount()
    source = RetrosheetSource(cache_config=LakeConfig(home=tmp_path / "lake"))

    source.ingest_season(2024)
    source.ingest_reference()

    events = audit.read_events(source="retrosheet")
    operations = {e.operation for e in events}
    assert {
        "retrosheet_list_tree",
        "retrosheet_download_file",
        "retrosheet_download_season",
        "retrosheet_build_events",
        "retrosheet_build_rosters",
        "retrosheet_quality_check",
        "retrosheet_ingest_season",
        "retrosheet_ingest_reference",
        "retrosheet_keep_documents",
    } <= operations
    assert all(e.status == "SUCCESS" for e in events)
    built = next(e for e in events if e.operation == "retrosheet_build_events")
    assert built.records_count > 0 and not built.cache_hit and built.duration_seconds >= 0

    # a second run reads everything from the lake: the build is logged as a cache hit
    source.ingest_season(2024)
    again = [
        e
        for e in audit.read_events(source="retrosheet")
        if e.operation == "retrosheet_build_events"
    ]
    assert again[-1].cache_hit and again[-1].records_count == 0
