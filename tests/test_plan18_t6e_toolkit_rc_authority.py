from __future__ import annotations

import json
from pathlib import Path

import pytest
from custos_toolkit.contracts import (
    ToolkitRcAuthorityReceiptV1,
    ToolkitRcPublicationObjectV1,
    ToolkitRcPublicationReceiptV1,
)

from scripts.toolkit_rc_promote import (
    ToolkitRcPromotionError,
    require_production_publication_receipt,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs/gateway-contract/v1/toolkit_rc_authority_receipt_v1.schema.json"
READY = ROOT / "docs/authority/receipts/custos-plan-18-task-6-toolkit-rc-receipt.json"


def test_authority_union_schema_is_source_generated_without_repo_receipt() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema == ToolkitRcAuthorityReceiptV1.model_json_schema(mode="validation")
    assert schema["discriminator"]["propertyName"] == "status"

    assert not READY.exists()


def test_unknown_or_mutated_pending_state_fails_closed() -> None:
    document = {"status": "PENDING_T6E_EXTERNAL_RELEASE", "ready": False}
    with pytest.raises(ValueError):
        ToolkitRcAuthorityReceiptV1.model_validate(document)
    document["status"] = "READY_BY_TEST"
    with pytest.raises(ValueError):
        ToolkitRcAuthorityReceiptV1.model_validate(document)


def test_nonproduction_publication_cannot_enter_promotion() -> None:
    coordinate = "artifact://custos/toolkit-rc/0.1.0rc1/wheels/base@sha256:" + "a" * 64
    publication = ToolkitRcPublicationReceiptV1(
        schema_version="alephain.custos.toolkit-rc-publication-receipt.v1",
        status="PENDING_T6C_PUBLICATION_VERIFIED",
        ready=False,
        handoff_ready=False,
        candidate_version="0.1.0rc1",
        source_repository="https://github.com/alchymia-labs/custos",
        source_commit="a" * 40,
        source_date_epoch=1_704_067_200,
        publication_id="publication-local",
        transaction_id="transaction-local",
        publication_atomic=True,
        puback_verified=True,
        readback_verified=True,
        production_credentials_used=False,
        production_signature_verified=False,
        workflow_ref=None,
        workflow_identity=None,
        oidc_issuer=None,
        release_environment=None,
        workflow_run_id=None,
        workflow_run_attempt=None,
        objects=(
            ToolkitRcPublicationObjectV1(
                coordinate=coordinate,
                object_id=__import__("hashlib").sha256(coordinate.encode()).hexdigest(),
                sha256="a" * 64,
                size_bytes=1,
            ),
        ),
        authority_registered=False,
    )
    with pytest.raises(ToolkitRcPromotionError, match="not production"):
        require_production_publication_receipt(publication)


def test_workflow_has_single_candidate_concurrency_and_durable_locator_output() -> None:
    workflow = (ROOT / ".github/workflows/release-toolkit-rc.yml").read_text(encoding="utf-8")
    assert "group: toolkit-rc-${{ inputs.candidate_version }}" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "durable_receipt_url=${{ steps.publish.outputs.durable_receipt_url }}" in workflow
    assert "actions/upload-artifact" not in workflow
