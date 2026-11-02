"""Tests for the master coverage matrix and cross-source parity."""

import importlib.util
import sys
from pathlib import Path

from baseballpy.core.datasets import DATASETS

ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = ROOT / "docs" / "MASTER_COVERAGE_MATRIX.md"
SCRIPT_PATH = ROOT / "scripts" / "master_coverage_audit.py"


def _load_audit_module():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("master_coverage_audit", SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["master_coverage_audit"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_master_coverage_matrix_completeness() -> None:
    """The committed master coverage matrix matches the generator output."""
    assert MATRIX_PATH.exists(), f"missing {MATRIX_PATH}"
    mod = _load_audit_module()
    generated = mod.generate_markdown_report()
    existing = MATRIX_PATH.read_text(encoding="utf-8")
    assert existing == generated, (
        "docs/MASTER_COVERAGE_MATRIX.md is stale; regenerate via scripts/master_coverage_audit.py"
    )


def test_every_dataset_in_registry_is_in_matrix() -> None:
    """Every registered dataset in DATASETS appears by name in the master matrix."""
    matrix_text = MATRIX_PATH.read_text(encoding="utf-8")
    missing = [
        f"{spec.source}:{spec.name}"
        for spec in DATASETS.values()
        if f"`{spec.name}`" not in matrix_text
    ]
    assert not missing, f"datasets in registry missing from matrix: {missing[:5]}..."


def test_external_capabilities_have_valid_metadata() -> None:
    """All external capabilities define targets, valid statuses, and non-empty notes."""
    mod = _load_audit_module()
    valid_statuses = {
        "Supported",
        "Partially Supported",
        "Derived / Not Scraped",
        "Supported via Official Feeds",
    }
    for cap in mod.CAPABILITIES:
        assert cap.domain, f"missing domain for {cap}"
        assert cap.feature, f"missing feature for {cap}"
        assert cap.status in valid_statuses, f"unexpected status {cap.status} in {cap}"
        assert cap.baseballpy_target, f"missing target for {cap}"
        assert cap.notes, f"missing notes for {cap}"
