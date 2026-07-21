from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "docs/authority/receipts/custos-plan-19-runner-policy-v1-receipt.json"


def test_runner_policy_has_one_pending_v1_authority() -> None:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    assert receipt["receipt_version"] == 1
    assert receipt["runner_state_schema_version"] == 1
    assert receipt["receipt_status"] == "READY_CODE_ONLY_PENDING_CR99_PRODUCER_RECEIPT"
    assert receipt["code_commit"] == "8c4454f35c5189063bad1516d77e260f034d3da7"
    assert receipt["validation"]["status"] == "FOCUSED_CANONICAL_V1_PASS"
    assert receipt["validation"]["passed"] == 90
    assert receipt["runtime_policy_consumed"] is False
    assert receipt["runner_policy_capability_ready"] is False
    assert receipt["runtime_ready"] is False
    assert receipt["production_ready"] is False


def test_old_policy_producer_and_slice_receipts_are_not_authority() -> None:
    manifest = json.loads((ROOT / "authority-manifest.json").read_text(encoding="utf-8"))
    paths = {
        entry["path"]
        for entry in manifest["authority_documents"]
        if isinstance(entry, dict) and "path" in entry
    }

    assert str(RECEIPT.relative_to(ROOT)) in paths
    assert not any("runner-policy-reservation-v2" in path for path in paths)
    assert not any("runner-policy-native-interception-v3" in path for path in paths)
    assert not any("runner-policy-daemon-composition-v4" in path for path in paths)
    assert not (ROOT / "docs/authority/vendor/crucible-plan-99").exists()
