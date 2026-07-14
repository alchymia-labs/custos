#!/usr/bin/env python3
"""Generate deterministic Plan 18 contract schemas, inventory, and golden data."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from custos.contracts.strategy_execution import (
    ArtifactMemberRole,
    ArtifactMemberV1,
    AttestationEvidenceV1,
    DevelopmentSourceRefV1,
    DigestBindingV1,
    StrategyArtifactRefV1,
    StrategyArtifactVerificationReceiptV1,
    StrategyExecutionCommandBindingV1,
    StrategyExecutionContextV1,
    StrategyManifestV1,
    canonical_json_digest,
    canonical_model_digest,
)

ROOT = Path(__file__).resolve().parents[1]
LEGACY_TOOLKIT_ROOT = ROOT / "src/custos/engines/nautilus/toolkit"
SOURCE_MODEL = ROOT / "src/custos/contracts/strategy_execution.py"

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


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def classify_toolkit_file(path: Path) -> dict[str, str]:
    relative = path.relative_to(LEGACY_TOOLKIT_ROOT).as_posix()
    if relative.startswith("vendor/pandas_ta/"):
        category = "private_vendor"
        target_distribution = "custos-strategy-toolkit-nautilus"
        target_path = "custos_toolkit_nautilus/_vendor/" + relative.removeprefix("vendor/")
        reason = "third-party engine dependency remains private"
    elif relative.startswith("shared/nautilus/"):
        category = "nautilus_specific"
        target_distribution = "custos-strategy-toolkit-nautilus"
        target_path = "custos_toolkit_nautilus/adapter/" + relative.removeprefix("shared/nautilus/")
        reason = "imports or implements Nautilus-specific behavior"
    elif relative.startswith("shared/hummingbot/"):
        category = "ps_owned_hummingbot"
        target_distribution = "none"
        target_path = ""
        reason = "not part of the Custos Nautilus execution closure"
    elif relative.startswith("shared/"):
        category = "platform_neutral"
        target_distribution = "custos-strategy-toolkit"
        target_path = "custos_toolkit/" + relative.removeprefix("shared/")
        reason = "engine-neutral contract or strategy helper"
    else:
        category = "delete"
        target_distribution = "none"
        target_path = ""
        reason = "legacy wrapper outside the extraction source roots"
    return {
        "legacy_path": path.relative_to(ROOT).as_posix(),
        "category": category,
        "target_distribution": target_distribution,
        "target_path": target_path,
        "migration_action": "extract_zero_rewrite" if target_path else "do_not_publish",
        "canonical_owner_after_cutover": "custos",
        "classification_reason": reason,
    }


def build_inventory() -> dict[str, object]:
    allowed_names = {"LICENSE"}
    files = sorted(
        path
        for path in LEGACY_TOOLKIT_ROOT.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and (path.suffix in {".py", ".yaml"} or path.name in allowed_names)
        and (
            "shared" in path.relative_to(LEGACY_TOOLKIT_ROOT).parts
            or "vendor" in path.relative_to(LEGACY_TOOLKIT_ROOT).parts
        )
    )
    entries = [classify_toolkit_file(path) for path in files]
    categories = [
        "platform_neutral",
        "nautilus_specific",
        "private_vendor",
        "ps_owned_strategy",
        "ps_owned_hummingbot",
        "delete",
    ]
    counts = {category: sum(entry["category"] == category for entry in entries) for category in categories}
    return {
        "inventory_schema_version": 1,
        "source_root": "src/custos/engines/nautilus/toolkit",
        "tracked_source_semantics": "all deterministic source inputs below shared/ and vendor/",
        "file_count": len(entries),
        "category_counts": counts,
        "current_canonical_source": "legacy Custos vendored snapshot until Plan 18 consumer cutover",
        "cutover_rule": "each file has one target authority; legacy source is removed only after receipt-backed cutover",
        "legacy_aliases_must_retire": ["shared", "pandas_ta"],
        "forbidden_migration_mechanisms": [
            "sys.path mutation",
            "fake pkg_resources distribution",
            "two writable canonical copies",
        ],
        "files": entries,
    }


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
        member(ArtifactMemberRole.BASE_CONTRACTS_WHEEL, "custos_strategy_toolkit-1.0.0rc1.whl", "b" * 64, 1000, "application/zip"),
        member(ArtifactMemberRole.NAUTILUS_WHEEL, "custos_strategy_toolkit_nautilus-1.0.0rc1.whl", "c" * 64, 2000, "application/zip"),
        member(ArtifactMemberRole.STRATEGY_WHEEL, "supertrend-1.0.0rc1.whl", digests["7"], 4096, "application/zip"),
        member(ArtifactMemberRole.STRATEGY_MANIFEST, "strategy-manifest-v1.json", digests["8"], 1024, "application/json"),
        runtime_member,
        member(ArtifactMemberRole.ATTESTATION_BUNDLE, "attestation.sigstore.json", digests["6"], 2048, "application/vnd.dev.sigstore.bundle+json"),
        member(ArtifactMemberRole.SBOM, "sbom.spdx.json", digests["1"], 3072, "application/spdx+json"),
        member(ArtifactMemberRole.CONTRACT_SCHEMA, "strategy-contract-assets-v1.json", digests["2"], 1536, "application/json"),
        member(ArtifactMemberRole.SOURCE_TREE, "source-tree.normalized", digests["3"], 8192, "application/vnd.alephain.source-tree"),
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
        verified_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
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


def build_assets() -> dict[str, bytes]:
    assets = {
        path: json_bytes(model.model_json_schema(mode="validation"))
        for path, model in MODEL_ASSETS.items()
    }
    assets[INVENTORY_PATH] = json_bytes(build_inventory())
    assets[GOLDEN_PATH] = json_bytes(build_lifecycle_golden())
    index_entries = [
        {"path": path, "sha256": sha256(data), "size_bytes": len(data)}
        for path, data in sorted(assets.items())
    ]
    index = {
        "asset_index_schema_version": 1,
        "canonical_name": "Custos Plan 18 Task 2 schema assets",
        "producer_source": SOURCE_MODEL.relative_to(ROOT).as_posix(),
        "producer_source_sha256": sha256(SOURCE_MODEL.read_bytes()),
        "assets": index_entries,
        "strategy_release_bom_ownership": "not owned by Custos; only member requirements are consumed",
    }
    assets[INDEX_PATH] = json_bytes(index)
    return assets


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
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
