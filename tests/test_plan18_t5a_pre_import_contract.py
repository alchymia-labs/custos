from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from custos_toolkit.contracts.strategy_execution import (
    StrategyArtifactPreImportVerificationReceiptV1,
    StrategyArtifactVerificationReceiptV1,
)
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
V2_INDEX = ROOT / "docs/authority/strategy-contract-assets-v2.json"
V2_GOLDEN = ROOT / "docs/authority/strategy-artifact-pre-import-lifecycle-golden-v2.json"
V2_NEGATIVE = ROOT / "docs/authority/strategy-artifact-pre-import-lifecycle-negative-v2.json"
V2_SCHEMA = (
    ROOT
    / "docs/gateway-contract/v2/strategy_artifact_pre_import_verification_receipt_v1.schema.json"
)
V2_RECEIPT = ROOT / "docs/authority/receipts/custos-plan-18-task-2-schema-receipt-v2.json"

IMMUTABLE_V1_SHA256 = {
    "docs/authority/receipts/custos-plan-18-task-2-schema-receipt.json": "f3c3d11b3609e644c982c82d1f3796a106a976e47e909cd94cf638b770b70e88",
    "docs/authority/strategy-contract-assets-v1.json": "d87d6fc2df020e92748058c5577863b83dd6f3b2a0c0f59adbf9b9b7822dae07",
    "docs/authority/strategy-artifact-lifecycle-golden-v1.json": "dc60fa0b50aac5e88362cfadd48f1094c5bae2a7542b746af87fbff3ad543136",
    "docs/authority/strategy-toolkit-inventory-v1.json": "98dba9e60e906c4943c3b768465b66ddb38c42e2bde0bae6ffbadfc7fe6eef68",
    "docs/gateway-contract/v1/development_source_ref_v1.schema.json": "ef05e08599927488e0da67d7620328dac230ea794d5106bbc6bf152a0381e54f",
    "docs/gateway-contract/v1/strategy_artifact_ref_v1.schema.json": "0f9ed02c57cbef30dc1e8a2597abe3cae796540f539ef56f2962db5a40765c6b",
    "docs/gateway-contract/v1/strategy_artifact_verification_receipt_v1.schema.json": "7f99d3939ad2a995621c71bee7bbd7d1d735f1f9b7fc090a34cd6800fc858b91",
    "docs/gateway-contract/v1/strategy_execution_command_binding_v1.schema.json": "d813bac90b4382f0e8ed4dcfb7805c170d6d79d9afcc42c9674407d216791507",
    "docs/gateway-contract/v1/strategy_execution_context_v1.schema.json": "c48980aa2321cb19697ec71c9154a69a642953e45849527a6c9972fbf4a1bda5",
    "docs/gateway-contract/v1/strategy_manifest_v1.schema.json": "70b14149acd718db84ec815da331a2b12b14ea5760fa0d1ac1cd7d23806a5c21",
    "docs/authority/receipts/vendor/crucible-plan-88-custos-task-2-requirements-review.json": "09bff539edafa818d1f15b866ae3626600ced90f613da68dd4e14a9385935095",
    "docs/authority/receipts/vendor/ps-plan-54-custos-task-2-requirements-review.json": "0a4d48c9bd1849b8a04b9a72ef6fb97942e0f66bc21b6d7916c2d5eb21650319",
}


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_task2_v1_authority_bytes_are_immutable() -> None:
    assert {
        relative: _sha256(ROOT / relative) for relative in IMMUTABLE_V1_SHA256
    } == IMMUTABLE_V1_SHA256


def test_public_pre_import_receipt_is_strict_and_phase_bounded() -> None:
    golden = _load(V2_GOLDEN)
    document = golden["pre_import_verification_receipt"]
    receipt = StrategyArtifactPreImportVerificationReceiptV1.model_validate(document)

    assert receipt.verified_entry_point == "strategies.supertrend:RuntimeAdapter"
    assert "loaded_entry_point" not in StrategyArtifactPreImportVerificationReceiptV1.model_fields
    assert "engine_ready" not in StrategyArtifactPreImportVerificationReceiptV1.model_fields
    assert "loaded_entry_point" in StrategyArtifactVerificationReceiptV1.model_fields


def test_pre_import_schema_is_generated_from_the_canonical_model() -> None:
    assert _load(V2_SCHEMA) == StrategyArtifactPreImportVerificationReceiptV1.model_json_schema(
        mode="validation"
    )


def test_negative_fixtures_reject_unknown_missing_and_cross_field_drift() -> None:
    negative = _load(V2_NEGATIVE)
    cases = negative["cases"]
    assert {case["name"] for case in cases} == {
        "unknown_post_import_field",
        "missing_verified_entry_point",
        "command_digest_mismatch",
        "member_projection_mismatch",
        "trusted_root_mismatch",
        "archive_entry_point_unverified",
    }
    for case in cases:
        with pytest.raises(ValidationError):
            StrategyArtifactPreImportVerificationReceiptV1.model_validate(case["document"])


def test_v2_index_binds_generated_assets_and_sidecars() -> None:
    index = _load(V2_INDEX)
    for entry in index["assets"]:
        path = ROOT / entry["path"]
        assert _sha256(path) == entry["sha256"]
        assert path.stat().st_size == entry["size_bytes"]
    for fixture in (V2_GOLDEN, V2_NEGATIVE):
        sidecar = fixture.with_name(f"{fixture.name}.sha256")
        assert sidecar.read_text(encoding="ascii") == f"{_sha256(fixture)}  {fixture.name}\n"


def test_v2_receipt_is_pending_and_contains_no_future_evidence() -> None:
    receipt = _load(V2_RECEIPT)
    assert receipt["receipt_status"] == "PENDING_REQUIREMENTS_REVIEWS"
    assert receipt["handoff_ready"] is False
    assert receipt["production_ready"] is False
    assert receipt["producer"]["candidate_commit"] is None
    assert receipt["producer"]["worktree_clean"] is None
    assert all(review["receipt"] is None for review in receipt["requirements_reviews"].values())
    assert receipt["predecessor"] == {
        "asset_index": {
            "path": "docs/authority/strategy-contract-assets-v1.json",
            "sha256": IMMUTABLE_V1_SHA256["docs/authority/strategy-contract-assets-v1.json"],
        },
        "task_2_receipt": {
            "path": "docs/authority/receipts/custos-plan-18-task-2-schema-receipt.json",
            "sha256": IMMUTABLE_V1_SHA256[
                "docs/authority/receipts/custos-plan-18-task-2-schema-receipt.json"
            ],
        },
    }
    assert receipt["contract_asset_index"]["sha256"] == _sha256(V2_INDEX)


def test_generator_check_is_clean() -> None:
    subprocess.run(
        [sys.executable, "scripts/generate_strategy_contract_assets.py", "--check"],
        cwd=ROOT,
        check=True,
    )
