"""Plan 19 T1 characterization floor.

These tests deliberately lock the pre-19a runtime shape. They do not import or
exercise production runtime objects, so collecting them cannot alter runner
state. A later Plan 19 slice that closes a gap must update the baseline and its
receipt in the same change.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_ROOT = _REPO_ROOT / "tests" / "fixtures" / "plan19"
_BASELINE_PATH = _FIXTURE_ROOT / "runtime_gap_baseline.v1.json"
_RECEIPT_PATH = (
    _REPO_ROOT
    / "docs"
    / "authority"
    / "receipts"
    / "custos-plan-19-task-1-characterization-receipt.json"
)


def _load_json(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


_BASELINE = _load_json(_BASELINE_PATH)
_RECEIPT = _load_json(_RECEIPT_PATH)


def _repo_text(relative_path: str) -> str:
    path = (_REPO_ROOT / relative_path).resolve()
    assert path.is_relative_to(_REPO_ROOT)
    assert path.is_file(), f"characterized source is missing: {relative_path}"
    return path.read_text(encoding="utf-8")


def test_gap_baseline_is_complete_and_machine_readable() -> None:
    assert _BASELINE["schema_version"] == 1
    assert _BASELINE["baseline_id"] == "C19-T1-RUNTIME-GAPS-V1"
    assert _BASELINE["status"] == "OPEN"
    assert _BASELINE["scope"]["production_behavior_changed"] is False

    gaps = _BASELINE["gaps"]
    assert isinstance(gaps, list)
    assert len(gaps) == 7
    gap_ids = [gap["gap_id"] for gap in gaps]
    assert len(gap_ids) == len(set(gap_ids))
    assert all(gap["state"] == "OPEN" for gap in gaps)
    assert all(gap["owner_slice"].startswith("19") for gap in gaps)
    assert all(gap["target_invariant"] for gap in gaps)


@pytest.mark.parametrize("gap", _BASELINE["gaps"], ids=lambda gap: gap["gap_id"])
def test_recorded_gap_evidence_matches_current_runtime_shape(gap: dict) -> None:
    for evidence in gap["evidence"]:
        source = _repo_text(evidence["path"])
        for marker in evidence["must_contain"]:
            assert marker in source, f"{gap['gap_id']} lost current marker: {marker}"
        for marker in evidence["must_not_contain"]:
            assert marker not in source, f"{gap['gap_id']} may have closed: {marker}"


def test_characterization_receipt_is_ready_without_claiming_runtime_readiness() -> None:
    assert _RECEIPT["schema_version"] == 1
    assert _RECEIPT["receipt_id"] == "R-C19-T1-CHARACTERIZATION"
    assert _RECEIPT["baseline_id"] == _BASELINE["baseline_id"]
    assert _RECEIPT["status"] == "READY_CHARACTERIZATION"
    assert _RECEIPT["scope"]["production_behavior_changed"] is False
    assert _RECEIPT["verification"]["executed"] is True
    assert _RECEIPT["verification"]["evidence"]
    assert _RECEIPT["scope"]["t2_ready"] is False
    assert _RECEIPT["readiness"]["runtime_activation_ready"] is False
    assert _RECEIPT["readiness"]["production_ready"] is False
