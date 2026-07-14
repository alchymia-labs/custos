#!/usr/bin/env python3
"""Generate deterministic Plan 18 contract schemas, inventory, and golden data."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from custos_toolkit.contracts.strategy_execution import (
    ArchiveVerificationEvidenceV1,
    ArtifactMemberRole,
    ArtifactMemberV1,
    AttestationEvidenceV1,
    DevelopmentSourceRefV1,
    DigestBindingV1,
    SigstoreVerificationEvidenceV1,
    StrategyArtifactPreImportVerificationReceiptV1,
    StrategyArtifactRefV1,
    StrategyArtifactVerificationReceiptV1,
    StrategyExecutionCommandBindingV1,
    StrategyExecutionContextV1,
    StrategyManifestV1,
    canonical_json_digest,
    canonical_model_digest,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MODEL = (
    ROOT / "packages/custos-strategy-toolkit/src/custos_toolkit/contracts/strategy_execution.py"
)
TASK_2_HISTORICAL_PRODUCER_SOURCE = "src/custos/contracts/strategy_execution.py"

MODEL_ASSETS = {
    "docs/gateway-contract/v1/strategy_execution_context_v1.schema.json": StrategyExecutionContextV1,
    "docs/gateway-contract/v1/strategy_manifest_v1.schema.json": StrategyManifestV1,
    "docs/gateway-contract/v1/strategy_artifact_ref_v1.schema.json": StrategyArtifactRefV1,
    "docs/gateway-contract/v1/development_source_ref_v1.schema.json": DevelopmentSourceRefV1,
    "docs/gateway-contract/v1/strategy_execution_command_binding_v1.schema.json": StrategyExecutionCommandBindingV1,
    "docs/gateway-contract/v1/strategy_artifact_verification_receipt_v1.schema.json": StrategyArtifactVerificationReceiptV1,
}
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


def build_lifecycle_golden() -> dict[str, object]:
    digests = {str(index): str(index) * 64 for index in range(1, 10)}
    source_commit = "a" * 40
    runtime_member = member(
        ArtifactMemberRole.RUNTIME_ARTIFACT,
        "resources/config.schema.json",
        digests["5"],
        512,
        "application/schema+json",
    )
    attestation = AttestationEvidenceV1(
        bundle_sha256=digests["6"],
        source_repository="https://github.com/alchymia-labs/philosophers-stone",
        source_commit=source_commit,
        normalized_source_tree_sha256=digests["3"],
        issuer="https://token.actions.githubusercontent.com",
        workflow_identity="alchymia-labs/philosophers-stone/.github/workflows/release-strategy.yml@refs/heads/main",
        trust_policy_id="custos-strategy-release",
        trust_policy_version=1,
        trust_policy_digest=digests["4"],
        python_version="3.12.4",
        engine="nautilus",
        engine_version="1.230.0",
        base_contracts_version="1.0.0rc1",
        engine_toolkit_version="1.0.0rc1",
        build_inputs=(DigestBindingV1(name="uv.lock", sha256=digests["9"]),),
    )
    artifact_ref = StrategyArtifactRefV1(
        artifact_kind="wheel",
        artifact_coordinate=f"ghcr.io/alephain/strategy/supertrend@sha256:{digests['7']}",
        artifact_sha256=digests["7"],
        artifact_size_bytes=4096,
        manifest_sha256=digests["8"],
        manifest_size_bytes=1024,
        required_runtime_artifacts=(runtime_member,),
        attestation=attestation,
        sbom_sha256=digests["1"],
        contract_schema_sha256=digests["2"],
    )
    members = (
        member(
            ArtifactMemberRole.BASE_CONTRACTS_WHEEL,
            "custos_strategy_toolkit-1.0.0rc1.whl",
            "b" * 64,
            1000,
            "application/zip",
        ),
        member(
            ArtifactMemberRole.NAUTILUS_WHEEL,
            "custos_strategy_toolkit_nautilus-1.0.0rc1.whl",
            "c" * 64,
            2000,
            "application/zip",
        ),
        member(
            ArtifactMemberRole.STRATEGY_WHEEL,
            "supertrend-1.0.0rc1.whl",
            digests["7"],
            4096,
            "application/zip",
        ),
        member(
            ArtifactMemberRole.STRATEGY_MANIFEST,
            "strategy-manifest-v1.json",
            digests["8"],
            1024,
            "application/json",
        ),
        runtime_member,
        member(
            ArtifactMemberRole.ATTESTATION_BUNDLE,
            "attestation.sigstore.json",
            digests["6"],
            2048,
            "application/vnd.dev.sigstore.bundle+json",
        ),
        member(
            ArtifactMemberRole.SBOM, "sbom.spdx.json", digests["1"], 3072, "application/spdx+json"
        ),
        member(
            ArtifactMemberRole.CONTRACT_SCHEMA,
            "strategy-contract-assets-v1.json",
            digests["2"],
            1536,
            "application/json",
        ),
        member(
            ArtifactMemberRole.SOURCE_TREE,
            "source-tree.normalized",
            digests["3"],
            8192,
            "application/vnd.alephain.source-tree",
        ),
    )
    member_table = [item.model_dump(mode="json") for item in members]
    ps_owned_bom_fixture = {
        "schema_version": 1,
        "members": member_table,
        "source_repository": attestation.source_repository,
        "source_commit": source_commit,
        "normalized_source_tree_sha256": attestation.normalized_source_tree_sha256,
    }
    release_bom_digest = canonical_json_digest(ps_owned_bom_fixture)
    effective_config = {"period": 10, "threshold": Decimal("1.25")}
    effective_config_digest = canonical_json_digest(effective_config)
    command_binding = StrategyExecutionCommandBindingV1(
        deployment_instance_id="20000000-0000-4000-8000-000000000002",
        deployment_spec_id="30000000-0000-4000-8000-000000000003",
        deployment_spec_digest="d" * 64,
        generation=1,
        strategy_release_id="50000000-0000-4000-8000-000000000005",
        release_bom_digest=release_bom_digest,
        release_bom_members=members,
        artifact_ref=artifact_ref,
        effective_config_digest=effective_config_digest,
    )
    receipt = StrategyArtifactVerificationReceiptV1(
        verification_profile="custos-artifact-verification-v1",
        verified_at=datetime(2026, 7, 14, tzinfo=UTC),
        command_binding=command_binding,
        artifact_ref_digest=canonical_model_digest(artifact_ref),
        verified_members=members,
        local_trust_policy_id=attestation.trust_policy_id,
        local_trust_policy_version=attestation.trust_policy_version,
        local_trust_policy_digest=attestation.trust_policy_digest,
        loaded_entry_point="strategies.supertrend:RuntimeAdapter",
    )
    return {
        "fixture_schema_version": 1,
        "contract_owner": "custos",
        "release_bom_owner": "philosophers-stone producer; Crucible StrategyRelease authority",
        "canonicalization": "sha256-canonical-json-v1",
        "artifact_ref": artifact_ref.model_dump(mode="json"),
        "strategy_release": {
            "strategy_release_id": str(command_binding.strategy_release_id),
            "release_bom_digest": release_bom_digest,
            "release_bom_members": member_table,
            "artifact_ref_digest": canonical_model_digest(artifact_ref),
            "deployment_spec_id": None,
        },
        "deployment_spec": {
            "deployment_spec_id": str(command_binding.deployment_spec_id),
            "deployment_spec_digest": command_binding.deployment_spec_digest,
            "strategy_release_id": str(command_binding.strategy_release_id),
            "effective_config_digest": effective_config_digest,
        },
        "signed_command": {"strategy_artifact_binding": command_binding.model_dump(mode="json")},
        "custos_verifier_receipt": receipt.model_dump(mode="json"),
        "lossless_mapping_assertions": [
            "StrategyRelease is independent of DeploymentSpec",
            "signed command preserves deployment instance, spec provenance, generation, release, BOM, member, artifact, and config digests",
            "Custos receipt echoes the complete signed command artifact binding and verified member table",
            "ArtifactRef contains no release, deployment, approval, or selection authority",
        ],
    }


def _sidecar(path: str, content: bytes) -> bytes:
    return f"{sha256(content)}  {Path(path).name}\n".encode("ascii")


def build_pre_import_receipt() -> StrategyArtifactPreImportVerificationReceiptV1:
    historical = json.loads((ROOT / GOLDEN_PATH).read_text(encoding="utf-8"))
    command = StrategyExecutionCommandBindingV1.model_validate(
        historical["signed_command"]["strategy_artifact_binding"]
    )
    wheel = next(
        member
        for member in command.release_bom_members
        if member.role is ArtifactMemberRole.STRATEGY_WHEEL
    )
    manifest = next(
        member
        for member in command.release_bom_members
        if member.role is ArtifactMemberRole.STRATEGY_MANIFEST
    )
    attestation = command.artifact_ref.attestation
    trusted_root_digest = "e" * 64
    return StrategyArtifactPreImportVerificationReceiptV1(
        verification_profile="custos-artifact-pre-import-verification-v1",
        verified_at=datetime(2026, 7, 15, tzinfo=UTC),
        command_binding=command,
        command_binding_digest=canonical_model_digest(command),
        artifact_ref_digest=canonical_model_digest(command.artifact_ref),
        release_bom_digest=command.release_bom_digest,
        verified_members=command.release_bom_members,
        local_trust_policy_id=attestation.trust_policy_id,
        local_trust_policy_version=attestation.trust_policy_version,
        local_trust_policy_digest=attestation.trust_policy_digest,
        trusted_root_digest=trusted_root_digest,
        sigstore=SigstoreVerificationEvidenceV1(
            verifier_capability_id="sigstore-python-verified-bundle-v1",
            bundle_sha256=attestation.bundle_sha256,
            trusted_root_sha256=trusted_root_digest,
            issuer=attestation.issuer,
            workflow_identity=attestation.workflow_identity,
            source_repository=attestation.source_repository,
            verified_subjects=(
                DigestBindingV1(name="strategy_release_bom", sha256=command.release_bom_digest),
                DigestBindingV1(name=wheel.name, sha256=wheel.sha256),
                DigestBindingV1(name=manifest.name, sha256=manifest.sha256),
            ),
            transparency_log_verified=True,
        ),
        archive=ArchiveVerificationEvidenceV1(
            archive_format="wheel",
            member_count=18,
            total_uncompressed_bytes=32768,
            entry_point_metadata_verified=True,
            entry_point_ast_verified=True,
        ),
        verified_entry_point="strategies.supertrend:RuntimeAdapter",
    )


def build_v2_lifecycle_golden() -> dict[str, object]:
    receipt = build_pre_import_receipt()
    return {
        "fixture_schema_version": 2,
        "contract_owner": "custos",
        "phase": "pre_import",
        "predecessor": {
            "asset_index": {"path": INDEX_PATH, "sha256": V1_IMMUTABLE_SHA256[INDEX_PATH]},
            "task_2_receipt": {
                "path": V1_RECEIPT_PATH,
                "sha256": V1_IMMUTABLE_SHA256[V1_RECEIPT_PATH],
            },
        },
        "command_binding": receipt.command_binding.model_dump(mode="json"),
        "pre_import_verification_receipt": receipt.model_dump(mode="json"),
        "phase_boundary_assertions": [
            "receipt proves verification before Python import",
            "verified_entry_point is inspected but not loaded",
            "quarantine paths and engine readiness are not public contract fields",
            "StrategyArtifactVerificationReceiptV1 remains the Plan 19 post-import contract",
        ],
    }


def build_v2_negative(golden: dict[str, object]) -> dict[str, object]:
    base = deepcopy(golden["pre_import_verification_receipt"])
    unknown = deepcopy(base)
    unknown["loaded_entry_point"] = "forbidden:Runtime"
    missing = deepcopy(base)
    missing.pop("verified_entry_point")
    command_digest = deepcopy(base)
    command_digest["command_binding_digest"] = "0" * 64
    member_projection = deepcopy(base)
    member_projection["verified_members"].pop()
    root_binding = deepcopy(base)
    root_binding["trusted_root_digest"] = "0" * 64
    archive = deepcopy(base)
    archive["archive"]["entry_point_ast_verified"] = False
    return {
        "fixture_schema_version": 2,
        "canonical_name": "Custos T5a pre-import contract negative fixtures",
        "cases": [
            {"name": "unknown_post_import_field", "document": unknown},
            {"name": "missing_verified_entry_point", "document": missing},
            {"name": "command_digest_mismatch", "document": command_digest},
            {"name": "member_projection_mismatch", "document": member_projection},
            {"name": "trusted_root_mismatch", "document": root_binding},
            {"name": "archive_entry_point_unverified", "document": archive},
        ],
    }


def build_assets() -> dict[str, bytes]:
    golden = json_bytes(build_v2_lifecycle_golden())
    negative = json_bytes(build_v2_negative(json.loads(golden)))
    assets = {
        V2_SCHEMA_PATH: json_bytes(
            StrategyArtifactPreImportVerificationReceiptV1.model_json_schema(mode="validation")
        ),
        V2_GOLDEN_PATH: golden,
        V2_NEGATIVE_PATH: negative,
        f"{V2_GOLDEN_PATH}.sha256": _sidecar(V2_GOLDEN_PATH, golden),
        f"{V2_NEGATIVE_PATH}.sha256": _sidecar(V2_NEGATIVE_PATH, negative),
    }
    index_entries = [
        {"path": path, "sha256": sha256(data), "size_bytes": len(data)}
        for path, data in sorted(assets.items())
    ]
    index = {
        "asset_index_schema_version": 2,
        "canonical_name": "Custos Plan 18 T5a public pre-import contract candidate assets",
        "candidate_status": "PENDING_REQUIREMENTS_REVIEWS",
        "predecessor": {
            "asset_index": {"path": INDEX_PATH, "sha256": V1_IMMUTABLE_SHA256[INDEX_PATH]},
            "task_2_receipt": {
                "path": V1_RECEIPT_PATH,
                "sha256": V1_IMMUTABLE_SHA256[V1_RECEIPT_PATH],
            },
        },
        "producer_source": str(SOURCE_MODEL.relative_to(ROOT)),
        "producer_source_sha256": sha256(SOURCE_MODEL.read_bytes()),
        "assets": index_entries,
        "v1_canonical_replaced": False,
    }
    index_bytes = json_bytes(index)
    assets[V2_INDEX_PATH] = index_bytes
    receipt = {
        "receipt_schema_version": 2,
        "canonical_name": "Custos Plan 18 Task 2 schema receipt v2",
        "receipt_status": "REQUIREMENTS_REVIEWS_ACCEPTED",
        "requirements_review_status": "ACCEPTED",
        "handoff_ready": False,
        "scope": "T5a requirements intake only; T5b production handoff remains open",
        "predecessor": index["predecessor"],
        "producer": {
            "repository": "tesseract-trading/custos",
            "source": str(SOURCE_MODEL.relative_to(ROOT)),
            "source_sha256": sha256(SOURCE_MODEL.read_bytes()),
            "candidate_commit": V2_PRODUCER_COMMIT,
            "worktree_clean": True,
        },
        "reviewed_candidate_receipt": {
            "commit": V2_PRODUCER_COMMIT,
            "path": V2_RECEIPT_PATH,
            "sha256": V2_CANDIDATE_RECEIPT_SHA256,
            "receipt_status": "PENDING_REQUIREMENTS_REVIEWS",
            "handoff_ready": False,
            "production_ready": False,
        },
        "t5b_implementation_evidence": {
            "commit": "560e9f5b80962df3307f855be7ceef70c3585bd7",
            "focused_tests_passed": 49,
            "production_pre_import_verifier_library_implemented": True,
            "public_pre_import_receipt_library_emission_implemented": True,
            "runtime_invocation_caller_wired": False,
            "strategy_import_wired": False,
            "current_head_full_make_verify_passed": False,
        },
        "contract_asset_index": {
            "path": V2_INDEX_PATH,
            "sha256": sha256(index_bytes),
        },
        "pre_import_receipt_schema": {
            "path": V2_SCHEMA_PATH,
            "sha256": next(
                entry["sha256"] for entry in index_entries if entry["path"] == V2_SCHEMA_PATH
            ),
        },
        "requirements_reviews": {
            name: {
                "required_receipt_name": profile["canonical_name"],
                "status": "ACCEPTED_REQUIREMENTS_REVIEW",
                "receipt": {
                    field: profile[field]
                    for field in (
                        "source_repository",
                        "source_path",
                        "source_commit",
                        "sha256",
                        "vendored_path",
                    )
                },
            }
            for name, profile in V2_REQUIREMENTS_REVIEWS.items()
        },
        "open_blockers": [
            "clean current-HEAD full make verify",
        ],
        "next_scoped_handoff_status": "READY_PRE_IMPORT_VERIFIER",
        "deferred_to_plan_19": [
            "runtime invocation caller",
            "strategy import and loaded entry point",
            "engine readiness and runtime lifecycle",
        ],
        "downstream_open_work": ["Custos Plan 18 Task 6 immutable toolkit RC receipt"],
        "loaded": False,
        "engine_ready": False,
        "runtime_ready": False,
        "production_ready": False,
        "immutable_toolkit_rc_ready": False,
    }
    assets[V2_RECEIPT_PATH] = json_bytes(receipt)
    return assets


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    immutable_drift = [
        relative
        for relative, expected_digest in V1_IMMUTABLE_SHA256.items()
        if not (ROOT / relative).is_file()
        or sha256((ROOT / relative).read_bytes()) != expected_digest
    ]
    if immutable_drift:
        for relative in immutable_drift:
            print(f"immutable Task 2 v1 authority byte drifted: {relative}")
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
    assets = build_assets()
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
