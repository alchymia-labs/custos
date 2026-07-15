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
    StrategyArtifactRefV2,
    canonical_model_digest,
)
from custos_toolkit.contracts.toolkit_rc import (
    ToolkitRcAuthorityReceiptV1,
    ToolkitRcReceiptManifestV1,
    ToolkitRcT6dPendingReceiptV1,
)

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
    assets = build_v3_artifact_ref_assets()
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
