#!/usr/bin/env python3
"""Generate deterministic Plan 18 contract schemas, inventory, and golden data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from custos_toolkit.contracts.strategy_execution import (
    ArtifactMemberRole,
    ArtifactMemberV1,
    DigestBindingV1,
    RunnerLocalArtifactPolicyDecisionV1,
    StrategyArtifactPreImportVerificationReceiptV2,
    StrategyArtifactRefV2,
    canonical_json_digest,
    canonical_model_digest,
)
from custos_toolkit.contracts.toolkit_rc import (
    ToolkitRcAuthorityReceiptV1,
    ToolkitRcReceiptManifestV1,
    ToolkitRcT6dPendingReceiptV1,
)
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MODEL = (
    ROOT / "packages/custos-strategy-toolkit/src/custos_toolkit/contracts/strategy_execution.py"
)
TASK_2_HISTORICAL_PRODUCER_SOURCE = "src/custos/contracts/strategy_execution.py"

INVENTORY_PATH = "docs/authority/strategy-toolkit-inventory-v1.json"
GOLDEN_PATH = "docs/authority/strategy-artifact-lifecycle-golden-v1.json"
INDEX_PATH = "docs/authority/strategy-contract-assets-v1.json"
V2_SCHEMA_PATH = (
    "docs/gateway-contract/v2/strategy_artifact_pre_import_verification_receipt_v1.schema.json"
)
V2_GOLDEN_PATH = "docs/authority/strategy-artifact-pre-import-lifecycle-golden-v2.json"
V2_NEGATIVE_PATH = "docs/authority/strategy-artifact-pre-import-lifecycle-negative-v2.json"
V2_INDEX_PATH = "docs/authority/strategy-contract-assets-v2.json"
V2_RECEIPT_PATH = "docs/authority/receipts/custos-plan-18-task-2-schema-receipt-v2.json"
V1_RECEIPT_PATH = "docs/authority/receipts/custos-plan-18-task-2-schema-receipt.json"
V3_SCHEMA_PATH = "docs/gateway-contract/v3/strategy_artifact_ref_v2.schema.json"
V3_GOLDEN_PATH = "docs/authority/strategy-artifact-ref-pre-sign-golden-v3.json"
V3_INDEX_PATH = "docs/authority/strategy-contract-assets-v3.json"
V3_RECEIPT_PATH = (
    "docs/authority/receipts/custos-plan-18-task-5c-artifact-ref-v2-producer-receipt.json"
)
V4_SCHEMA_PATH = (
    "docs/gateway-contract/v4/strategy_artifact_pre_import_verification_receipt_v2.schema.json"
)
V4_GOLDEN_PATH = "docs/authority/strategy-artifact-pre-import-verification-golden-v4.json"
V4_NEGATIVE_PATH = "docs/authority/strategy-artifact-pre-import-verification-negative-v4.json"
V4_INDEX_PATH = "docs/authority/strategy-contract-assets-v4.json"
V4_CONSUMER_RECEIPT_PATH = (
    "docs/authority/receipts/custos-plan-18-task-5d-a-evidence-consumer-receipt.json"
)
CR_PLAN89_COMMAND_INDEX_PATH = "docs/authority/crucible-runner-command-consumer-assets-v1.json"
CR_PLAN89_COMMAND_CONSUMER_RECEIPT_PATH = (
    "docs/authority/receipts/custos-plan-18-task-5d-b-command-consumer-receipt.json"
)
CR_PLAN89_VENDOR_ROOT = "docs/authority/vendor/crucible-plan-89"
CR_PLAN89_CONTRACT_COMMIT = "51d23eba8aaefb30e936fc9fae1eac0e791164aa"
CR_PLAN89_PUBLICATION_COMMIT = "06b2cbc0bafc0eda2b92fc2bc3f36ba1626abc3d"
CR_PLAN89_PRODUCER_RECEIPT_SHA256 = (
    "105ea501b83053421066b4053ec3583e4dd109560b0689bfeb856c2f8beec5d2"
)
CR_PLAN89_COMMAND_CONSUMER_SOURCE = "src/custos/contracts/crucible_runner_command.py"
CR_PLAN89_COMMAND_CONSUMER_TEST = "tests/test_plan18_t5d_b_runner_command_consumer.py"
CR_PLAN89_AUTHORITY_ASSETS = {
    "docs/authority/golden/crucible-runner-deployment-command-v1.json": (
        CR_PLAN89_CONTRACT_COMMIT,
        "7054351ccf625bb7696063c0deb9e15c22ed1022dbdc1ef6a7adc4e78fb8c73e",
        140382,
    ),
    "docs/authority/golden/crucible-runner-deployment-command-v1.json.sha256": (
        CR_PLAN89_CONTRACT_COMMIT,
        "a9b3bb28795622fbf1a6afcd425c7f9c94f9a7accaa5945523d92a7023319b7e",
        65,
    ),
    "docs/authority/receipts/crucible-plan-89-runner-command-producer-v1.json": (
        CR_PLAN89_PUBLICATION_COMMIT,
        CR_PLAN89_PRODUCER_RECEIPT_SHA256,
        4059,
    ),
    "docs/authority/schemas/crucible-runner-deployment-command-v1.schema.json": (
        CR_PLAN89_CONTRACT_COMMIT,
        "5aecc9ca09b1b06204fd9f790ecfc56ad3bc10e72086f84168092beff69061da",
        5522,
    ),
    "docs/authority/schemas/crucible-runner-deployment-command-v1.schema.json.sha256": (
        CR_PLAN89_CONTRACT_COMMIT,
        "f4bc19211678de8e01c35349c08cf0771bc5d99c4d5c6fac68d9e8b946673747",
        65,
    ),
}
CR_PLAN89_NON_CURRENT_COMMITS = (
    "fe7be5119633c341f6e888a250a601d9db0d6e67",
    "56743f090ef3461f306d3937bfa8b054e6e7b2d8",
    "a20f7116fed35670264d3a0139974aa25daa2a26",
)
PS_PLAN54_VENDOR_ROOT = "docs/authority/vendor/ps-plan-54"
PS_PLAN54_SOURCE_COMMIT = "175be5090c1c9708db89921271d7f2b26b2d0a40"
PS_PLAN54_REVIEWED_FOLLOWUP_COMMIT = "6ce6f553188c04f48a4ee1838efc42bee82deed3"
PS_PLAN54_AUTHORITY_ASSETS = {
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
CR_PLAN88_SCHEMA_CANDIDATE_COMMIT = "cd3fb8721c8df557ef57d5ef7ec3ae372b54061c"
CR_PLAN88_SOURCE_COMMIT = "b761bf7f75f5e19b1161b146c144ce244932b6e3"
CR_PLAN88_VENDOR_ROOT = "docs/authority/vendor/crucible-plan-88"
CR_PLAN88_SCHEMA_CANDIDATES = {
    "docs/authority/schemas/crucible-artifact-acceptance-receipt-v1.schema.json": (
        "aa4cd2504aecd8faa0ad35bf415bfa06436b89df3083b4349485e56b05ce0b84",
        1694,
    ),
    "docs/authority/schemas/crucible-artifact-evidence-v1.schema.json": (
        "b005a4106d37a5ce1091ac6a7710f79c2a21bb20aea7ba1b6ab93f46f37493d3",
        6936,
    ),
}
CR_PLAN88_AUTHORITY_ASSETS = {
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
TOOLKIT_RC_SCHEMA_PATH = "docs/gateway-contract/v1/toolkit_rc_receipt_manifest_v1.schema.json"
TOOLKIT_RC_T6D_PENDING_SCHEMA_PATH = (
    "docs/gateway-contract/v1/toolkit_rc_t6d_pending_receipt_v1.schema.json"
)
TOOLKIT_RC_AUTHORITY_SCHEMA_PATH = (
    "docs/gateway-contract/v1/toolkit_rc_authority_receipt_v1.schema.json"
)
V2_PRODUCER_COMMIT = "f3adde2870a53a4bb52cc2a260d2c7c1c852eee2"
V2_CANDIDATE_RECEIPT_SHA256 = "83005dc4090c75db8beca0fd8a825b3dc7094bc31fc99e96fb50d416c8f9f9d0"
V2_REQUIREMENTS_REVIEWS = {
    "crucible_rust_plan_88": {
        "canonical_name": (
            "Crucible Plan 88 Custos Plan 18 T5a v2 pre-import requirements-only consumer review"
        ),
        "source_repository": "tesseract-trading/crucible-rust",
        "source_path": (
            "docs/authority/receipts/crucible-plan-88-custos-task-2-v2-requirements-review.json"
        ),
        "source_commit": "3f41f32d15c05f209e5462d460b8ae08433376d2",
        "sha256": "2102b363b5c4751a2b2e20302ff010446764d783e56c2e1e2b2c1a6b580fc8ad",
        "vendored_path": (
            "docs/authority/receipts/vendor/"
            "crucible-plan-88-custos-task-2-v2-requirements-review.json"
        ),
    },
    "philosophers_stone_plan_54": {
        "canonical_name": (
            "Philosophers-Stone Plan 54 Custos Plan 18 T5a v2 pre-import requirements review"
        ),
        "source_repository": "alchymia-labs/philosophers-stone",
        "source_path": (
            "docs/authority/receipts/ps-plan-54-custos-task-2-v2-requirements-review.json"
        ),
        "source_commit": "267e23bd500f1b465bee81b0b9b7c2f8c054c2aa",
        "sha256": "8ac5597094ad0916e9aa4c254735132a87afbe96592772edd5dce4e709699822",
        "vendored_path": (
            "docs/authority/receipts/vendor/ps-plan-54-custos-task-2-v2-requirements-review.json"
        ),
    },
}

V1_IMMUTABLE_SHA256 = {
    V1_RECEIPT_PATH: "f3c3d11b3609e644c982c82d1f3796a106a976e47e909cd94cf638b770b70e88",
    INDEX_PATH: "d87d6fc2df020e92748058c5577863b83dd6f3b2a0c0f59adbf9b9b7822dae07",
    GOLDEN_PATH: "dc60fa0b50aac5e88362cfadd48f1094c5bae2a7542b746af87fbff3ad543136",
    INVENTORY_PATH: "98dba9e60e906c4943c3b768465b66ddb38c42e2bde0bae6ffbadfc7fe6eef68",
    "docs/gateway-contract/v1/development_source_ref_v1.schema.json": "ef05e08599927488e0da67d7620328dac230ea794d5106bbc6bf152a0381e54f",
    "docs/gateway-contract/v1/strategy_artifact_ref_v1.schema.json": "0f9ed02c57cbef30dc1e8a2597abe3cae796540f539ef56f2962db5a40765c6b",
    "docs/gateway-contract/v1/strategy_artifact_verification_receipt_v1.schema.json": "7f99d3939ad2a995621c71bee7bbd7d1d735f1f9b7fc090a34cd6800fc858b91",
    "docs/gateway-contract/v1/strategy_execution_command_binding_v1.schema.json": "d813bac90b4382f0e8ed4dcfb7805c170d6d79d9afcc42c9674407d216791507",
    "docs/gateway-contract/v1/strategy_execution_context_v1.schema.json": "c48980aa2321cb19697ec71c9154a69a642953e45849527a6c9972fbf4a1bda5",
    "docs/gateway-contract/v1/strategy_manifest_v1.schema.json": "70b14149acd718db84ec815da331a2b12b14ea5760fa0d1ac1cd7d23806a5c21",
    "docs/authority/receipts/vendor/crucible-plan-88-custos-task-2-requirements-review.json": "09bff539edafa818d1f15b866ae3626600ced90f613da68dd4e14a9385935095",
    "docs/authority/receipts/vendor/ps-plan-54-custos-task-2-requirements-review.json": "0a4d48c9bd1849b8a04b9a72ef6fb97942e0f66bc21b6d7916c2d5eb21650319",
}

V2_IMMUTABLE_SHA256 = {
    V2_INDEX_PATH: "6fd49708967d59576b61529075d3423f43d936bdfac1a834ed655de0682bbcbc",
    V2_GOLDEN_PATH: "3d36fb0effdd512d83574795cd92a463caabe85f6c227a3735b198da484cee7d",
    f"{V2_GOLDEN_PATH}.sha256": "2b8585f903999c4a2a95f94a64ba49dade5327d4db93128142d4bca1b8df2145",
    V2_NEGATIVE_PATH: "d554a0f95da2e8cba6f72616b7337d95c1878f23462a2df971a384a9b4c3678e",
    f"{V2_NEGATIVE_PATH}.sha256": "551f0614a4967aa47b223d3850cfd230390e8664ecc5eeb720727bfbac595c6c",
    V2_SCHEMA_PATH: "d6e21b0a9207ed8bdd6e4e21cce53070939d21e2aed1992544f9fa7f41cf3463",
    V2_RECEIPT_PATH: "439c5e0b93bc3d6593091df0fc997908f70a303b2403f813cdb05bbde2dcefe3",
    "docs/authority/receipts/vendor/crucible-plan-88-custos-task-2-v2-requirements-review.json": "2102b363b5c4751a2b2e20302ff010446764d783e56c2e1e2b2c1a6b580fc8ad",
    "docs/authority/receipts/vendor/ps-plan-54-custos-task-2-v2-requirements-review.json": "8ac5597094ad0916e9aa4c254735132a87afbe96592772edd5dce4e709699822",
}


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def member(
    role: ArtifactMemberRole, name: str, digest: str, size: int, media_type: str
) -> ArtifactMemberV1:
    return ArtifactMemberV1(
        role=role,
        name=name,
        media_type=media_type,
        size_bytes=size,
        sha256=digest,
    )


def _sidecar(path: str, content: bytes) -> bytes:
    return f"{sha256(content)}  {Path(path).name}\n".encode("ascii")


def build_v3_artifact_ref_assets() -> dict[str, bytes]:
    artifact_digest = "7" * 64
    runtime_member = member(
        ArtifactMemberRole.RUNTIME_ARTIFACT,
        "resources/config.schema.json",
        "5" * 64,
        512,
        "application/schema+json",
    )
    artifact_ref = StrategyArtifactRefV2(
        artifact_kind="wheel",
        artifact_coordinate=(f"ghcr.io/alephain/strategy/supertrend@sha256:{artifact_digest}"),
        artifact_sha256=artifact_digest,
        artifact_size_bytes=4096,
        manifest_sha256="8" * 64,
        manifest_size_bytes=1024,
        required_runtime_artifacts=(runtime_member,),
        sbom_sha256="1" * 64,
        contract_schema_sha256="2" * 64,
        source_repository="https://github.com/alchymia-labs/philosophers-stone",
        source_commit="a" * 40,
        normalized_source_tree_sha256="3" * 64,
        python_version="3.12.4",
        engine="nautilus",
        engine_version="1.230.0",
        base_contracts_version="1.0.0rc1",
        engine_toolkit_version="1.0.0rc1",
        build_inputs=(DigestBindingV1(name="uv.lock", sha256="9" * 64),),
    )
    golden = json_bytes(
        {
            "fixture_schema_version": 3,
            "canonical_name": "Custos StrategyArtifactRefV2 pre-sign golden",
            "candidate_status": "PRE_SIGN_ABI_ONLY",
            "production_handoff_ready": False,
            "canonicalization": "sha256-canonical-json-v1",
            "artifact_ref": artifact_ref.model_dump(mode="json"),
            "artifact_ref_digest": canonical_model_digest(artifact_ref),
            "scope_ceiling": (
                "No command, BOM, attestation, acceptance, verification, runtime, or "
                "production readiness claim"
            ),
        }
    )
    schema = json_bytes(StrategyArtifactRefV2.model_json_schema(mode="validation"))
    generated = {
        V3_SCHEMA_PATH: schema,
        V3_GOLDEN_PATH: golden,
        f"{V3_GOLDEN_PATH}.sha256": _sidecar(V3_GOLDEN_PATH, golden),
    }
    legacy = {
        "v1": {
            "asset_index": INDEX_PATH,
            "sha256": V1_IMMUTABLE_SHA256[INDEX_PATH],
            "runtime_fallback_allowed": False,
        },
        "v2": {
            "asset_index": V2_INDEX_PATH,
            "sha256": V2_IMMUTABLE_SHA256[V2_INDEX_PATH],
            "runtime_fallback_allowed": False,
        },
    }
    source_digest = sha256(SOURCE_MODEL.read_bytes())
    index_entries = [
        {"path": path, "sha256": sha256(data), "size_bytes": len(data)}
        for path, data in sorted(generated.items())
    ]
    index = {
        "asset_index_schema_version": 3,
        "canonical_name": "Custos Plan 18 T5c corrected pre-sign artifact assets",
        "candidate_status": "PRE_SIGN_ABI_ONLY",
        "handoff_ready": False,
        "production_ready": False,
        "current_artifact_ref_type": "StrategyArtifactRefV2",
        "current_artifact_ref_schema": V3_SCHEMA_PATH,
        "producer_source": str(SOURCE_MODEL.relative_to(ROOT)),
        "producer_source_sha256": source_digest,
        "legacy_non_production": legacy,
        "assets": index_entries,
    }
    index_bytes = json_bytes(index)
    generated[V3_INDEX_PATH] = index_bytes
    generated[V3_RECEIPT_PATH] = json_bytes(
        {
            "receipt_schema_version": 1,
            "canonical_name": "Custos Plan 18 Task 5c ArtifactRefV2 producer receipt",
            "receipt_status": "PRODUCED_AWAITING_CONSUMER_REVIEWS",
            "producer_repository": "tesseract-trading/custos",
            "producer_source": str(SOURCE_MODEL.relative_to(ROOT)),
            "producer_source_sha256": source_digest,
            "contract_asset_index": {
                "path": V3_INDEX_PATH,
                "sha256": sha256(index_bytes),
            },
            "artifact_ref_schema": {
                "path": V3_SCHEMA_PATH,
                "sha256": sha256(schema),
            },
            "legacy_non_production": legacy,
            "requirements_reviews": {},
            "handoff_ready": False,
            "runtime_ready": False,
            "production_ready": False,
            "open_blockers": [
                "T5d full PS BOM, detached attestation, and Crucible evidence command ABI",
                "T5e verifier/runtime cutover with explicit StrategyArtifactRefV1 rejection",
                "exact PS Plan 54 and Crucible Plan 88 consumer requirements reviews",
            ],
        }
    )
    return generated


def build_v4_evidence_consumer_assets() -> dict[str, bytes]:
    ps_root = ROOT / PS_PLAN54_VENDOR_ROOT / "docs/authority"
    cr_root = ROOT / CR_PLAN88_VENDOR_ROOT / "docs/authority"
    release_bom = json.loads((ps_root / "strategy-release-bom-v1.golden.json").read_bytes())
    release_statement = json.loads(
        (ps_root / "strategy-release-statement-v1.golden.json").read_bytes()
    )
    detached_ref = json.loads((ps_root / "artifact-attestation-ref-v1.golden.json").read_bytes())
    evidence = json.loads((cr_root / "golden/crucible-artifact-evidence-v1.json").read_bytes())
    acceptance = json.loads(
        (cr_root / "golden/crucible-artifact-acceptance-receipt-v1.json").read_bytes()
    )

    members_by_role = {item["role"]: item for item in release_bom["members"]}
    runtime_member = members_by_role["runtime_artifact"]
    artifact_ref = StrategyArtifactRefV2(
        artifact_kind="wheel",
        artifact_coordinate=release_bom["strategy_artifact_coordinate"],
        artifact_sha256=release_bom["strategy_artifact_sha256"],
        artifact_size_bytes=members_by_role["strategy_wheel"]["size_bytes"],
        manifest_sha256=release_bom["strategy_manifest_sha256"],
        manifest_size_bytes=members_by_role["strategy_manifest"]["size_bytes"],
        required_runtime_artifacts=(
            member(
                ArtifactMemberRole.RUNTIME_ARTIFACT,
                runtime_member["name"],
                runtime_member["sha256"],
                runtime_member["size_bytes"],
                runtime_member["media_type"],
            ),
        ),
        sbom_sha256=release_bom["toolkit_sbom_sha256"],
        contract_schema_sha256=release_bom["execution_abi_schema_sha256"],
        source_repository=release_bom["producer_repository"],
        source_commit=release_bom["strategy_source_commit"],
        normalized_source_tree_sha256=release_bom["strategy_source_tree_sha256"],
        python_version="3.12.4",
        engine=release_bom["engine"],
        engine_version=release_bom["engine_version"],
        base_contracts_version="1.0.0rc1",
        engine_toolkit_version="1.0.0rc1",
        build_inputs=(DigestBindingV1(name="build-lock", sha256=release_bom["build_lock_sha256"]),),
    )
    release_bom_digest = canonical_json_digest(release_bom)
    release_statement_digest = canonical_json_digest(release_statement)
    artifact_ref_digest = canonical_model_digest(artifact_ref)
    detached_ref_digest = canonical_json_digest(detached_ref)

    evidence.update(
        {
            "artifact_ref_digest": artifact_ref_digest,
            "manifest_digest": artifact_ref.manifest_sha256,
            "release_bom_digest": release_bom_digest,
            "statement_digest": release_statement_digest,
            "attestation_ref_digest": detached_ref_digest,
            "bundle_sha256": detached_ref["bundle_sha256"],
        }
    )
    evidence_schema = json.loads(
        (cr_root / "schemas/crucible-artifact-evidence-v1.schema.json").read_bytes()
    )
    required_claims = evidence_schema["properties"]["signed_producer_claims"]["required"]
    evidence["signed_producer_claims"] = {
        name: release_statement["predicate"][name] for name in required_claims
    }
    evidence["sigstore_proof"]["bundle_sha256"] = detached_ref["bundle_sha256"]
    evidence["sigstore_proof"]["statement_sha256"] = release_statement_digest
    acceptance["strategy_release_id"] = evidence["strategy_release_id"]
    acceptance["artifact_evidence_digest"] = evidence["artifact_evidence_digest"]

    owner_documents = {
        "release_bom": (release_bom, ps_root / "strategy-release-bom-v1.schema.json"),
        "release_statement": (
            release_statement,
            ps_root / "strategy-release-statement-v1.schema.json",
        ),
        "detached_attestation_ref": (
            detached_ref,
            ps_root / "artifact-attestation-ref-v1.schema.json",
        ),
        "crucible_artifact_evidence": (
            evidence,
            cr_root / "schemas/crucible-artifact-evidence-v1.schema.json",
        ),
        "crucible_artifact_acceptance": (
            acceptance,
            cr_root / "schemas/crucible-artifact-acceptance-receipt-v1.schema.json",
        ),
    }
    for document, schema_path in owner_documents.values():
        Draft202012Validator(json.loads(schema_path.read_bytes())).validate(document)

    policy = RunnerLocalArtifactPolicyDecisionV1(
        authority="custos-runner-local",
        policy_id="custos-runner-artifact-live-v1",
        policy_version=1,
        policy_digest="6" * 64,
        evaluated_at="2026-07-15T12:00:01Z",
        decision="accepted",
        release_bom_digest=release_bom_digest,
        artifact_ref_digest=artifact_ref_digest,
        artifact_evidence_digest=evidence["artifact_evidence_digest"],
        artifact_acceptance_receipt_digest=acceptance["receipt_digest"],
    )
    receipt = StrategyArtifactPreImportVerificationReceiptV2(
        verification_profile="custos-artifact-pre-import-verification-v2",
        verified_at="2026-07-15T12:00:01Z",
        release_bom=release_bom,
        release_bom_digest=release_bom_digest,
        release_statement=release_statement,
        release_statement_digest=release_statement_digest,
        artifact_ref=artifact_ref,
        artifact_ref_digest=artifact_ref_digest,
        detached_attestation_ref=detached_ref,
        detached_attestation_ref_digest=detached_ref_digest,
        crucible_artifact_evidence=evidence,
        crucible_artifact_evidence_digest=evidence["artifact_evidence_digest"],
        crucible_artifact_acceptance=acceptance,
        crucible_artifact_acceptance_receipt_digest=acceptance["receipt_digest"],
        runner_local_policy_decision=policy,
    )
    receipt_document = receipt.model_dump(mode="json")

    schema = StrategyArtifactPreImportVerificationReceiptV2.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    owner_refs = {
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
    for field, reference in owner_refs.items():
        schema["properties"][field] = {"$ref": reference}
    schema_bytes = json_bytes(schema)

    golden = json_bytes(
        {
            "fixture_schema_version": 4,
            "canonical_name": "Custos Plan 18 T5d-A ReceiptV2 contract consumer golden",
            "status": "READY_CONTRACT_CONSUMER_ONLY",
            "contract_consumer_ready": True,
            "command_consumer_ready": False,
            "runtime_ready": False,
            "production_ready": False,
            "receipt": receipt_document,
            "receipt_digest": canonical_model_digest(receipt),
        }
    )
    mutations = [
        {
            "name": "artifact_ref_bundle_field_forbidden",
            "mutation": {
                "operation": "add",
                "path": ["artifact_ref", "bundle_sha256"],
                "value": "1" * 64,
            },
        },
        {
            "name": "artifact_ref_policy_field_forbidden",
            "mutation": {
                "operation": "add",
                "path": ["artifact_ref", "policy_digest"],
                "value": "2" * 64,
            },
        },
        {
            "name": "bom_array_forbidden",
            "mutation": {"operation": "replace", "path": ["release_bom"], "value": []},
        },
        {
            "name": "bundle_self_reference_forbidden",
            "mutation": {
                "operation": "replace",
                "path": ["detached_attestation_ref", "bundle_sha256"],
                "value": detached_ref_digest,
            },
        },
        {
            "name": "crucible_policy_reuse_forbidden",
            "mutation": {
                "operation": "replace",
                "path": ["runner_local_policy_decision", "policy_digest"],
                "value": evidence["local_policy_evaluation"]["policy_digest"],
            },
        },
        {
            "name": "missing_certificate_proof",
            "mutation": {
                "operation": "remove",
                "path": ["crucible_artifact_evidence", "sigstore_proof", "certificate_sha256"],
            },
        },
        {
            "name": "missing_checkpoint_proof",
            "mutation": {
                "operation": "remove",
                "path": ["crucible_artifact_evidence", "sigstore_proof", "checkpoint_verified"],
            },
        },
        {
            "name": "missing_sct_proof",
            "mutation": {
                "operation": "remove",
                "path": ["crucible_artifact_evidence", "sigstore_proof", "sct_verified"],
            },
        },
        {
            "name": "missing_set_proof",
            "mutation": {
                "operation": "remove",
                "path": ["crucible_artifact_evidence", "sigstore_proof", "set_verified"],
            },
        },
        {
            "name": "missing_tlog_proof",
            "mutation": {
                "operation": "remove",
                "path": ["crucible_artifact_evidence", "sigstore_proof", "rekor_log_id"],
            },
        },
        {
            "name": "release_bom_members_alias_forbidden",
            "mutation": {
                "operation": "add",
                "path": ["release_bom_members"],
                "value": [],
            },
        },
        {
            "name": "request_selected_policy_forbidden",
            "mutation": {
                "operation": "add",
                "path": ["runner_local_policy_decision", "requested_by_command"],
                "value": True,
            },
        },
        {
            "name": "verified_members_alias_forbidden",
            "mutation": {"operation": "add", "path": ["verified_members"], "value": []},
        },
    ]
    negative = json_bytes(
        {
            "fixture_schema_version": 4,
            "canonical_name": "Custos Plan 18 T5d-A ReceiptV2 negative mutations",
            "base_golden": V4_GOLDEN_PATH,
            "base_golden_sha256": sha256(golden),
            "cases": mutations,
        }
    )
    generated = {
        V4_SCHEMA_PATH: schema_bytes,
        V4_GOLDEN_PATH: golden,
        f"{V4_GOLDEN_PATH}.sha256": _sidecar(V4_GOLDEN_PATH, golden),
        V4_NEGATIVE_PATH: negative,
        f"{V4_NEGATIVE_PATH}.sha256": _sidecar(V4_NEGATIVE_PATH, negative),
    }
    index_entries = [
        {"path": path, "sha256": sha256(data), "size_bytes": len(data)}
        for path, data in sorted(generated.items())
    ]
    ps_producer_assets = [
        {
            "source_path": source_path,
            "vendored_path": f"{PS_PLAN54_VENDOR_ROOT}/{source_path}",
            "sha256": digest,
            "size_bytes": size_bytes,
        }
        for source_path, (digest, size_bytes) in sorted(PS_PLAN54_AUTHORITY_ASSETS.items())
    ]
    crucible_producer_assets = [
        {
            "source_path": source_path,
            "vendored_path": f"{CR_PLAN88_VENDOR_ROOT}/{source_path}",
            "sha256": digest,
            "size_bytes": size_bytes,
        }
        for source_path, (digest, size_bytes) in sorted(CR_PLAN88_AUTHORITY_ASSETS.items())
    ]
    crucible_schema_baseline = [
        {"source_path": source_path, "sha256": digest, "size_bytes": size_bytes}
        for source_path, (digest, size_bytes) in sorted(CR_PLAN88_SCHEMA_CANDIDATES.items())
    ]
    index = json_bytes(
        {
            "asset_index_schema_version": 4,
            "canonical_name": "Custos Plan 18 T5d-A ReceiptV2 contract consumer assets",
            "status": "READY_CONTRACT_CONSUMER_ONLY",
            "current_receipt_type": "StrategyArtifactPreImportVerificationReceiptV2",
            "current_receipt_schema": V4_SCHEMA_PATH,
            "ps_producer_commit": PS_PLAN54_SOURCE_COMMIT,
            "crucible_producer_commit": CR_PLAN88_SOURCE_COMMIT,
            "consumer_source": str(SOURCE_MODEL.relative_to(ROOT)),
            "consumer_source_sha256": sha256(SOURCE_MODEL.read_bytes()),
            "producer_authority": {
                "philosophers_stone": {
                    "source_repository": "alchymia-labs/philosophers-stone",
                    "source_commit": PS_PLAN54_SOURCE_COMMIT,
                    "reviewed_followup_commit": PS_PLAN54_REVIEWED_FOLLOWUP_COMMIT,
                    "producer_assets": ps_producer_assets,
                },
                "crucible_rust": {
                    "schema_baseline": {
                        "source_commit": CR_PLAN88_SCHEMA_CANDIDATE_COMMIT,
                        "schemas": crucible_schema_baseline,
                    },
                    "publication": {
                        "source_repository": "tesseract-trading/crucible-rust",
                        "source_commit": CR_PLAN88_SOURCE_COMMIT,
                        "producer_assets": crucible_producer_assets,
                    },
                },
            },
            "contract_consumer_ready": True,
            "command_consumer_ready": False,
            "runtime_ready": False,
            "production_ready": False,
            "assets": index_entries,
        }
    )
    generated[V4_INDEX_PATH] = index
    generated[V4_CONSUMER_RECEIPT_PATH] = json_bytes(
        {
            "receipt_schema_version": 1,
            "canonical_name": "Custos Plan 18 T5d-A evidence consumer receipt",
            "receipt_status": "READY_CONTRACT_CONSUMER_ONLY",
            "contract_asset_index": {
                "path": V4_INDEX_PATH,
                "sha256": sha256(index),
                "size_bytes": len(index),
            },
            "ps_producer": {
                "repository": "alchymia-labs/philosophers-stone",
                "commit": PS_PLAN54_SOURCE_COMMIT,
            },
            "crucible_producer": {
                "repository": "tesseract-trading/crucible-rust",
                "commit": CR_PLAN88_SOURCE_COMMIT,
                "publication_receipt": (
                    f"{CR_PLAN88_VENDOR_ROOT}/docs/authority/receipts/"
                    "crucible-plan-88-evidence-contract-producer-publication.json"
                ),
            },
            "policy_boundary": {
                "crucible_local_policy_decision_reused": False,
                "runner_local_policy_decision_required": True,
            },
            "strategy_artifact_pre_import_verification_receipt_v2_published": True,
            "contract_consumer_ready": True,
            "command_consumer_ready": False,
            "runtime_ready": False,
            "production_ready": False,
            "open_blockers": [
                "Custos Plan 18 T5d-B exact Crucible Plan 89 command consumer",
                "Custos Plan 18 T5e production verifier and parser cutover",
                "Custos Plan 19 durable runtime composition",
            ],
        }
    )
    return generated


def build_cr89_command_consumer_assets() -> dict[str, bytes]:
    producer_assets = [
        {
            "source_path": source_path,
            "vendored_path": f"{CR_PLAN89_VENDOR_ROOT}/{source_path}",
            "source_commit": source_commit,
            "sha256": digest,
            "size_bytes": size_bytes,
        }
        for source_path, (source_commit, digest, size_bytes) in sorted(
            CR_PLAN89_AUTHORITY_ASSETS.items()
        )
    ]
    consumer_assets = []
    for relative in (CR_PLAN89_COMMAND_CONSUMER_SOURCE, CR_PLAN89_COMMAND_CONSUMER_TEST):
        data = (ROOT / relative).read_bytes()
        consumer_assets.append({"path": relative, "sha256": sha256(data), "size_bytes": len(data)})
    index = json_bytes(
        {
            "asset_index_schema_version": 1,
            "canonical_name": ("Custos Plan 18 T5d-B and Plan 19 T2 CR89 command consumer assets"),
            "status": "READY_COMMAND_CONSUMER_CONTRACT_ONLY",
            "slice_equivalence": ["Custos Plan 18 T5d-B", "Custos Plan 19 T2"],
            "producer_authority": {
                "repository": "tesseract-trading/crucible-rust",
                "contract_commit": CR_PLAN89_CONTRACT_COMMIT,
                "publication_commit": CR_PLAN89_PUBLICATION_COMMIT,
                "producer_receipt_sha256": CR_PLAN89_PRODUCER_RECEIPT_SHA256,
                "producer_assets": producer_assets,
                "superseded_non_current_commits": list(CR_PLAN89_NON_CURRENT_COMMITS),
            },
            "consumer_model": {
                "path": CR_PLAN89_COMMAND_CONSUMER_SOURCE,
                "public_export": "CrucibleRunnerDeploymentCommandV1",
                "sha256": consumer_assets[0]["sha256"],
                "size_bytes": consumer_assets[0]["size_bytes"],
            },
            "consumer_assets": consumer_assets,
            "custos_publishes_command_schema": False,
            "exact_signed_event_bytes_retained": True,
            "signature_bytes_in_fingerprint": False,
            "full_artifact_evidence_required": True,
            "acceptance_semantics_fail_closed": True,
            "command_contract_consumer_ready": True,
            "runtime_ready": False,
            "production_ready": False,
        }
    )
    receipt = json_bytes(
        {
            "receipt_schema_version": 1,
            "canonical_name": ("Custos Plan 18 T5d-B and Plan 19 T2 command consumer receipt"),
            "receipt_status": "READY_COMMAND_CONSUMER_CONTRACT_ONLY",
            "plan_18_task_5d_b_stop": True,
            "plan_19_task_2_stop": True,
            "contract_asset_index": {
                "path": CR_PLAN89_COMMAND_INDEX_PATH,
                "sha256": sha256(index),
                "size_bytes": len(index),
            },
            "crucible_producer": {
                "repository": "tesseract-trading/crucible-rust",
                "contract_commit": CR_PLAN89_CONTRACT_COMMIT,
                "publication_commit": CR_PLAN89_PUBLICATION_COMMIT,
                "producer_receipt": (
                    f"{CR_PLAN89_VENDOR_ROOT}/docs/authority/receipts/"
                    "crucible-plan-89-runner-command-producer-v1.json"
                ),
                "producer_receipt_sha256": CR_PLAN89_PRODUCER_RECEIPT_SHA256,
                "superseded_non_current_commits": list(CR_PLAN89_NON_CURRENT_COMMITS),
            },
            "upstream_t5d_a_stop": {
                "commit": "3d2ddcf11e7c6fe30fb36f09e8340b2d49f6c245",
                "path": (
                    "docs/authority/receipts/"
                    "custos-plan-18-task-5d-a-evidence-consumer-receipt.json"
                ),
                "sha256": ("4589aebd1c8fbbd2e7d6b501e8367d5805e0f83694a755a8a63960b1d8453509"),
            },
            "consumer_model": {
                "path": CR_PLAN89_COMMAND_CONSUMER_SOURCE,
                "public_export": "CrucibleRunnerDeploymentCommandV1",
                "sha256": consumer_assets[0]["sha256"],
                "size_bytes": consumer_assets[0]["size_bytes"],
            },
            "contract_guards": {
                "full_artifact_evidence_cross_binding": True,
                "strict_acceptance_semantics": True,
                "exact_signed_event_bytes_retained": True,
                "signature_bytes_in_fingerprint": False,
                "legacy_v1_fallback": False,
                "second_bom_authority_allowed": False,
                "command_selected_root_policy_issuer_workflow": False,
                "custos_command_schema_published": False,
            },
            "command_contract_consumer_ready": True,
            "runtime_wiring_changed": False,
            "runtime_ready": False,
            "production_ready": False,
            "open_blockers": [
                "Custos Plan 18 T5e verifier and runtime cutover",
                "Custos Plan 19 T3 fingerprint and bounded ACK policy",
                "Custos Plan 19 T4-T5 durable state and engine lifecycle",
            ],
        }
    )
    return {
        CR_PLAN89_COMMAND_INDEX_PATH: index,
        CR_PLAN89_COMMAND_CONSUMER_RECEIPT_PATH: receipt,
    }


def build_toolkit_rc_foundation_assets() -> dict[str, bytes]:
    return {
        TOOLKIT_RC_SCHEMA_PATH: json_bytes(
            ToolkitRcReceiptManifestV1.model_json_schema(mode="validation")
        ),
        TOOLKIT_RC_T6D_PENDING_SCHEMA_PATH: json_bytes(
            ToolkitRcT6dPendingReceiptV1.model_json_schema(mode="validation")
        ),
        TOOLKIT_RC_AUTHORITY_SCHEMA_PATH: json_bytes(
            ToolkitRcAuthorityReceiptV1.model_json_schema(mode="validation")
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    immutable_drift = [
        relative
        for relative, expected_digest in {
            **V1_IMMUTABLE_SHA256,
            **V2_IMMUTABLE_SHA256,
        }.items()
        if not (ROOT / relative).is_file()
        or sha256((ROOT / relative).read_bytes()) != expected_digest
    ]
    if immutable_drift:
        for relative in immutable_drift:
            print(f"immutable legacy strategy authority byte drifted: {relative}")
        return 1
    review_drift = [
        profile["vendored_path"]
        for profile in V2_REQUIREMENTS_REVIEWS.values()
        if not (ROOT / profile["vendored_path"]).is_file()
        or sha256((ROOT / profile["vendored_path"]).read_bytes()) != profile["sha256"]
    ]
    if review_drift:
        for relative in review_drift:
            print(f"accepted Task 2 v2 requirements review byte drifted: {relative}")
        return 1
    vendor_drift = [
        f"{PS_PLAN54_VENDOR_ROOT}/{source_path}"
        for source_path, (expected_digest, expected_size) in (PS_PLAN54_AUTHORITY_ASSETS.items())
        if not (ROOT / PS_PLAN54_VENDOR_ROOT / source_path).is_file()
        or (ROOT / PS_PLAN54_VENDOR_ROOT / source_path).stat().st_size != expected_size
        or sha256((ROOT / PS_PLAN54_VENDOR_ROOT / source_path).read_bytes()) != expected_digest
    ]
    if vendor_drift:
        for relative in vendor_drift:
            print(f"vendored PS Plan 54 producer authority byte drifted: {relative}")
        return 1
    crucible_vendor_drift = [
        f"{CR_PLAN88_VENDOR_ROOT}/{source_path}"
        for source_path, (expected_digest, expected_size) in (CR_PLAN88_AUTHORITY_ASSETS.items())
        if not (ROOT / CR_PLAN88_VENDOR_ROOT / source_path).is_file()
        or (ROOT / CR_PLAN88_VENDOR_ROOT / source_path).stat().st_size != expected_size
        or sha256((ROOT / CR_PLAN88_VENDOR_ROOT / source_path).read_bytes()) != expected_digest
    ]
    if crucible_vendor_drift:
        for relative in crucible_vendor_drift:
            print(f"vendored Crucible Plan 88 producer authority byte drifted: {relative}")
        return 1
    cr89_vendor_drift = [
        f"{CR_PLAN89_VENDOR_ROOT}/{source_path}"
        for source_path, (_, expected_digest, expected_size) in (CR_PLAN89_AUTHORITY_ASSETS.items())
        if not (ROOT / CR_PLAN89_VENDOR_ROOT / source_path).is_file()
        or (ROOT / CR_PLAN89_VENDOR_ROOT / source_path).stat().st_size != expected_size
        or sha256((ROOT / CR_PLAN89_VENDOR_ROOT / source_path).read_bytes()) != expected_digest
    ]
    if cr89_vendor_drift:
        for relative in cr89_vendor_drift:
            print(f"vendored Crucible Plan 89 producer authority byte drifted: {relative}")
        return 1
    assets = build_v3_artifact_ref_assets()
    assets.update(build_v4_evidence_consumer_assets())
    assets.update(build_cr89_command_consumer_assets())
    assets.update(build_toolkit_rc_foundation_assets())
    drift: list[str] = []
    for relative, expected in assets.items():
        path = ROOT / relative
        if args.check:
            if not path.is_file() or path.read_bytes() != expected:
                drift.append(relative)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(expected)
    if drift:
        for relative in drift:
            print(f"generated strategy contract asset differs: {relative}")
        return 1
    if not args.check:
        print(f"generated {len(assets)} strategy contract assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
