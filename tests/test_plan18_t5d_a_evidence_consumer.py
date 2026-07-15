from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from custos_toolkit import contracts as strategy_contracts
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError as PydanticValidationError

ROOT = Path(__file__).resolve().parents[1]
V4_INDEX = ROOT / "docs/authority/strategy-contract-assets-v4.json"
CONSUMER_RECEIPT = (
    ROOT / "docs/authority/receipts/custos-plan-18-task-5d-a-evidence-consumer-receipt.json"
)
V4_SCHEMA = (
    ROOT
    / "docs/gateway-contract/v4/strategy_artifact_pre_import_verification_receipt_v2.schema.json"
)
V4_GOLDEN = ROOT / "docs/authority/strategy-artifact-pre-import-verification-golden-v4.json"
V4_NEGATIVE = ROOT / "docs/authority/strategy-artifact-pre-import-verification-negative-v4.json"
PS_SOURCE_COMMIT = "175be5090c1c9708db89921271d7f2b26b2d0a40"
PS_REVIEWED_FOLLOWUP_COMMIT = "6ce6f553188c04f48a4ee1838efc42bee82deed3"
CR_SCHEMA_CANDIDATE_COMMIT = "cd3fb8721c8df557ef57d5ef7ec3ae372b54061c"
CR_SOURCE_COMMIT = "b761bf7f75f5e19b1161b146c144ce244932b6e3"
CR_ASSETS = {
    "docs/authority/golden/crucible-artifact-acceptance-receipt-v1.json": (
        "27964669627105cfc6664856ee391e426f2a3ceb59cbf14f0042e22c3b0664d4",
        815,
    ),
    "docs/authority/golden/crucible-artifact-acceptance-receipt-v1.json.sha256": (
        "4c54fdbf51555fd21ba6ac122ae88eda758d39bdca0965e957d51c629ebb0968",
        65,
    ),
    "docs/authority/golden/crucible-artifact-evidence-v1.json": (
        "b84c1a60ec7f2a2abd5d2c5b678c02bf8528b6493aca30e5f8a6a5255eecd40c",
        3432,
    ),
    "docs/authority/golden/crucible-artifact-evidence-v1.json.sha256": (
        "45f1d40d7b1d7dcdf1617a9c0a909092b509e22c6d29bee2d49a533f257cb97d",
        65,
    ),
    "docs/authority/receipts/crucible-plan-88-evidence-contract-producer-publication.json": (
        "98d49d27b2b701a5cf4ef5c29f8716137d9d6e2623b8d4dd179d93eeac4fad1a",
        1793,
    ),
    "docs/authority/schemas/crucible-artifact-acceptance-receipt-v1.schema.json": (
        "aa4cd2504aecd8faa0ad35bf415bfa06436b89df3083b4349485e56b05ce0b84",
        1694,
    ),
    "docs/authority/schemas/crucible-artifact-evidence-v1.schema.json": (
        "b005a4106d37a5ce1091ac6a7710f79c2a21bb20aea7ba1b6ab93f46f37493d3",
        6936,
    ),
}
PS_ASSETS = {
    "docs/authority/artifact-attestation-ref-v1.golden.json": (
        "fdfa5fbd9b1e85b6fb58153552807d79127e7e05f8408c949d1a01e491a30dec",
        651,
    ),
    "docs/authority/artifact-attestation-ref-v1.golden.json.sha256": (
        "97f8f5b84ba5147e1e09522efc5c194e8bee7a2b85b984c6939dc869ef36fd97",
        65,
    ),
    "docs/authority/artifact-attestation-ref-v1.schema.json": (
        "eeefc23e7744b77689d6467bde39c0d97b71b23ac140a86365ffca32838d57fb",
        1295,
    ),
    "docs/authority/receipts/ps-plan-54-slice-a-contract-lock.json": (
        "4a717c09c82cd2e95636fc7b093f6f0c70bb4931a950595c3d3347f72f3887b3",
        4468,
    ),
    "docs/authority/receipts/ps-plan-54-task-3-bom-producer-receipt.json": (
        "44cb830fe69cccf51248b2b7a4cbd08317465709a42f53aca0c46fd2f0865d66",
        3945,
    ),
    "docs/authority/strategy-release-bom-v1.golden.json": (
        "7322ba18c793bf1d77616b796185c3716df91226d28c6b381b156e75142f9b71",
        4672,
    ),
    "docs/authority/strategy-release-bom-v1.golden.json.sha256": (
        "f02564f4b4423bc19a17ebe36da71c72d4e52e09bbf199daf5b1aa3134445dc9",
        65,
    ),
    "docs/authority/strategy-release-bom-v1.schema.json": (
        "7d5ad399060315e10b6866dec07d87a086302f3a9e13092f956a6f43d5d5286a",
        5145,
    ),
    "docs/authority/strategy-release-statement-v1.golden.json": (
        "082d6cd58676be90ffe563c4648922ec5dc61978026b01341766b0263f5794f5",
        1820,
    ),
    "docs/authority/strategy-release-statement-v1.golden.json.sha256": (
        "4d72420615ad544b7ce90116984ee2a6dc2b3817daf96db66fba2860f99493d1",
        65,
    ),
    "docs/authority/strategy-release-statement-v1.schema.json": (
        "9aab6b799f4462af285cbad3e6c40e41b9175e1e1fcb72219e1942fd84645148",
        4479,
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


OWNER_SCHEMAS = {
    "release_bom": (
        ROOT / "docs/authority/vendor/ps-plan-54/docs/authority/strategy-release-bom-v1.schema.json"
    ),
    "release_statement": (
        ROOT / "docs/authority/vendor/ps-plan-54/docs/authority/"
        "strategy-release-statement-v1.schema.json"
    ),
    "detached_attestation_ref": (
        ROOT / "docs/authority/vendor/ps-plan-54/docs/authority/"
        "artifact-attestation-ref-v1.schema.json"
    ),
    "crucible_artifact_evidence": (
        ROOT / "docs/authority/vendor/crucible-plan-88/docs/authority/schemas/"
        "crucible-artifact-evidence-v1.schema.json"
    ),
    "crucible_artifact_acceptance": (
        ROOT / "docs/authority/vendor/crucible-plan-88/docs/authority/schemas/"
        "crucible-artifact-acceptance-receipt-v1.schema.json"
    ),
}


def _validate_v2_document(document: dict[str, object]) -> None:
    for field, schema_path in OWNER_SCHEMAS.items():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(document[field])
    strategy_contracts.StrategyArtifactPreImportVerificationReceiptV2.model_validate(document)


def _apply_mutation(document: dict[str, object], mutation: dict[str, object]) -> None:
    path = mutation["path"]
    assert isinstance(path, list) and path
    target: object = document
    for segment in path[:-1]:
        assert isinstance(target, dict)
        target = target[segment]
    assert isinstance(target, dict)
    key = path[-1]
    assert isinstance(key, str)
    if mutation["operation"] == "remove":
        del target[key]
    else:
        target[key] = mutation["value"]


def test_ps_plan54_owner_assets_are_vendored_byte_exact_with_provenance() -> None:
    index = json.loads(V4_INDEX.read_text(encoding="utf-8"))
    producer = index["producer_authority"]["philosophers_stone"]

    assert index["status"] == "READY_CONTRACT_CONSUMER_ONLY"
    assert producer["source_repository"] == "alchymia-labs/philosophers-stone"
    assert producer["source_commit"] == PS_SOURCE_COMMIT
    assert producer["reviewed_followup_commit"] == PS_REVIEWED_FOLLOWUP_COMMIT

    expected_entries = []
    for source_path, (digest, size_bytes) in sorted(PS_ASSETS.items()):
        vendored_path = f"docs/authority/vendor/ps-plan-54/{source_path}"
        expected_entries.append(
            {
                "source_path": source_path,
                "vendored_path": vendored_path,
                "sha256": digest,
                "size_bytes": size_bytes,
            }
        )
        path = ROOT / vendored_path
        assert path.stat().st_size == size_bytes
        assert _sha256(path) == digest

    assert producer["producer_assets"] == expected_entries

    for golden_name in (
        "artifact-attestation-ref-v1.golden.json",
        "strategy-release-bom-v1.golden.json",
        "strategy-release-statement-v1.golden.json",
    ):
        golden = ROOT / "docs/authority/vendor/ps-plan-54/docs/authority" / golden_name
        sidecar = golden.with_name(f"{golden.name}.sha256")
        assert sidecar.read_text(encoding="ascii") == f"{_sha256(golden)}\n"


def test_t5d_a_consumer_receipt_closes_only_the_contract_consumer_scope() -> None:
    index = json.loads(V4_INDEX.read_text(encoding="utf-8"))
    receipt = json.loads(CONSUMER_RECEIPT.read_text(encoding="utf-8"))

    expected_candidate_schemas = [
        {
            "source_path": (
                "docs/authority/schemas/crucible-artifact-acceptance-receipt-v1.schema.json"
            ),
            "sha256": "aa4cd2504aecd8faa0ad35bf415bfa06436b89df3083b4349485e56b05ce0b84",
            "size_bytes": 1694,
        },
        {
            "source_path": ("docs/authority/schemas/crucible-artifact-evidence-v1.schema.json"),
            "sha256": "b005a4106d37a5ce1091ac6a7710f79c2a21bb20aea7ba1b6ab93f46f37493d3",
            "size_bytes": 6936,
        },
    ]
    assert index["producer_authority"]["crucible_rust"]["schema_baseline"] == {
        "source_commit": CR_SCHEMA_CANDIDATE_COMMIT,
        "schemas": expected_candidate_schemas,
    }
    assert receipt["receipt_status"] == "READY_CONTRACT_CONSUMER_ONLY"
    assert receipt["strategy_artifact_pre_import_verification_receipt_v2_published"] is True
    assert receipt["policy_boundary"] == {
        "crucible_local_policy_decision_reused": False,
        "runner_local_policy_decision_required": True,
    }
    assert receipt["contract_consumer_ready"] is True
    assert receipt["command_consumer_ready"] is False
    assert receipt["runtime_ready"] is False
    assert receipt["production_ready"] is False

    serialized = json.dumps({"index": index, "receipt": receipt})
    assert "release_bom_members" not in serialized
    assert "verified_members" not in serialized


def test_crucible_plan88_owner_assets_are_vendored_from_one_clean_publication() -> None:
    index = json.loads(V4_INDEX.read_text(encoding="utf-8"))

    expected_entries = []
    for source_path, (digest, size_bytes) in sorted(CR_ASSETS.items()):
        vendored_path = f"docs/authority/vendor/crucible-plan-88/{source_path}"
        expected_entries.append(
            {
                "source_path": source_path,
                "vendored_path": vendored_path,
                "sha256": digest,
                "size_bytes": size_bytes,
            }
        )
        path = ROOT / vendored_path
        assert path.stat().st_size == size_bytes
        assert _sha256(path) == digest

    assert index["producer_authority"]["crucible_rust"]["publication"] == {
        "source_repository": "tesseract-trading/crucible-rust",
        "source_commit": CR_SOURCE_COMMIT,
        "producer_assets": expected_entries,
    }
    publication_path = (
        ROOT / "docs/authority/vendor/crucible-plan-88/docs/authority/receipts/"
        "crucible-plan-88-evidence-contract-producer-publication.json"
    )
    publication = json.loads(publication_path.read_text(encoding="utf-8"))
    assert publication["producer_baseline_commit"] == CR_SCHEMA_CANDIDATE_COMMIT
    assert publication["publication_scope"] == "contract_only"
    assert publication["contracts"]["artifact_evidence_v1"] == {
        "schema_path": "docs/authority/schemas/crucible-artifact-evidence-v1.schema.json",
        "schema_sha256": CR_ASSETS[
            "docs/authority/schemas/crucible-artifact-evidence-v1.schema.json"
        ][0],
        "golden_path": "docs/authority/golden/crucible-artifact-evidence-v1.json",
        "golden_sha256": CR_ASSETS["docs/authority/golden/crucible-artifact-evidence-v1.json"][0],
        "golden_sha256_sidecar_path": (
            "docs/authority/golden/crucible-artifact-evidence-v1.json.sha256"
        ),
    }


def test_receipt_v2_public_abi_has_only_owner_objects_and_custos_bindings() -> None:
    receipt_type = strategy_contracts.StrategyArtifactPreImportVerificationReceiptV2
    policy_type = strategy_contracts.RunnerLocalArtifactPolicyDecisionV1

    assert set(receipt_type.model_fields) == {
        "schema_version",
        "verification_profile",
        "verified_at",
        "release_bom",
        "release_bom_digest",
        "release_statement",
        "release_statement_digest",
        "artifact_ref",
        "artifact_ref_digest",
        "detached_attestation_ref",
        "detached_attestation_ref_digest",
        "crucible_artifact_evidence",
        "crucible_artifact_evidence_digest",
        "crucible_artifact_acceptance",
        "crucible_artifact_acceptance_receipt_digest",
        "runner_local_policy_decision",
    }
    assert set(policy_type.model_fields) == {
        "schema_version",
        "authority",
        "policy_id",
        "policy_version",
        "policy_digest",
        "evaluated_at",
        "decision",
        "release_bom_digest",
        "artifact_ref_digest",
        "artifact_evidence_digest",
        "artifact_acceptance_receipt_digest",
    }
    schema = receipt_type.model_json_schema(mode="validation")
    assert schema["title"] == "StrategyArtifactPreImportVerificationReceiptV2"
    assert schema["additionalProperties"] is False
    assert "release_bom_members" not in schema["properties"]
    assert "verified_members" not in schema["properties"]


def test_receipt_v2_schema_golden_and_negatives_enforce_owner_and_custos_boundaries() -> None:
    schema = json.loads(V4_SCHEMA.read_text(encoding="utf-8"))
    golden = json.loads(V4_GOLDEN.read_text(encoding="utf-8"))
    negatives = json.loads(V4_NEGATIVE.read_text(encoding="utf-8"))

    expected_refs = {
        "release_bom": (
            "../../authority/vendor/ps-plan-54/docs/authority/strategy-release-bom-v1.schema.json"
        ),
        "release_statement": (
            "../../authority/vendor/ps-plan-54/docs/authority/"
            "strategy-release-statement-v1.schema.json"
        ),
        "detached_attestation_ref": (
            "../../authority/vendor/ps-plan-54/docs/authority/"
            "artifact-attestation-ref-v1.schema.json"
        ),
        "crucible_artifact_evidence": (
            "../../authority/vendor/crucible-plan-88/docs/authority/schemas/"
            "crucible-artifact-evidence-v1.schema.json"
        ),
        "crucible_artifact_acceptance": (
            "../../authority/vendor/crucible-plan-88/docs/authority/schemas/"
            "crucible-artifact-acceptance-receipt-v1.schema.json"
        ),
    }
    assert {field: schema["properties"][field]["$ref"] for field in expected_refs} == expected_refs
    assert golden["status"] == "READY_CONTRACT_CONSUMER_ONLY"
    assert golden["contract_consumer_ready"] is True
    assert golden["command_consumer_ready"] is False
    assert golden["runtime_ready"] is False
    assert golden["production_ready"] is False
    _validate_v2_document(golden["receipt"])

    expected_cases = {
        "artifact_ref_bundle_field_forbidden",
        "artifact_ref_policy_field_forbidden",
        "bom_array_forbidden",
        "bundle_self_reference_forbidden",
        "crucible_policy_reuse_forbidden",
        "missing_certificate_proof",
        "missing_checkpoint_proof",
        "missing_sct_proof",
        "missing_set_proof",
        "missing_tlog_proof",
        "release_bom_members_alias_forbidden",
        "request_selected_policy_forbidden",
        "verified_members_alias_forbidden",
    }
    assert {case["name"] for case in negatives["cases"]} == expected_cases
    for case in negatives["cases"]:
        invalid = copy.deepcopy(golden["receipt"])
        _apply_mutation(invalid, case["mutation"])
        try:
            _validate_v2_document(invalid)
        except (JsonSchemaValidationError, PydanticValidationError, TypeError, ValueError):
            continue
        raise AssertionError(f"negative fixture unexpectedly accepted: {case['name']}")


def test_contract_consumer_slice_is_current_without_runtime_or_production_promotion() -> None:
    manifest = json.loads((ROOT / "authority-manifest.json").read_text(encoding="utf-8"))
    ecosystem = json.loads(
        (ROOT / "docs/authority/ecosystem-authority.json").read_text(encoding="utf-8")
    )
    entries = manifest["authority_documents"]

    assert {
        "role": "strategy_contract_asset_index_v4_current_contract_consumer",
        "path": "docs/authority/strategy-contract-assets-v4.json",
        "status": "READY_CONTRACT_CONSUMER_ONLY",
        "contract_consumer_ready": True,
        "runtime_ready": False,
        "production_ready": False,
    } in entries
    assert {
        "role": "strategy_artifact_pre_import_verification_receipt_v2_schema",
        "path": (
            "docs/gateway-contract/v4/"
            "strategy_artifact_pre_import_verification_receipt_v2.schema.json"
        ),
        "contract_consumer_ready": True,
        "runtime_ready": False,
    } in entries
    assert {
        "role": "plan_18_task_5d_a_evidence_consumer_receipt",
        "path": ("docs/authority/receipts/custos-plan-18-task-5d-a-evidence-consumer-receipt.json"),
        "receipt_status": "READY_CONTRACT_CONSUMER_ONLY",
        "contract_consumer_ready": True,
        "runtime_ready": False,
        "production_ready": False,
    } in entries

    authority = ecosystem["strategy_execution_contract"]
    assert authority["task_5d_a_status"] == "READY_CONTRACT_CONSUMER_ONLY"
    assert authority["asset_index"] == "docs/authority/strategy-contract-assets-v4.json"
    assert authority["task_5d_a_consumer_receipt"] == (
        "docs/authority/receipts/custos-plan-18-task-5d-a-evidence-consumer-receipt.json"
    )
    assert authority["task_5d_a_contract_consumer_ready"] is True
    assert authority["task_5d_a_runtime_ready"] is False
    assert authority["task_5d_b_status"] == "BLOCKED_ON_CR89_COMMAND_PRODUCER"
    assert authority["asset_index_status"] == "READY_CONTRACT_CONSUMER_ONLY"
    assert authority["production_ready"] is False

    assert "StrategyArtifactPreImportVerificationReceiptV2" in strategy_contracts.__all__
    assert not any("preparation" in entry["role"] for entry in entries)
