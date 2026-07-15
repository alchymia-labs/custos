#!/usr/bin/env python3
"""Validate self-contained Custos authority and optional workspace alignment."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "authority-manifest.json"
TASK_2_RECEIPT_PATH = "docs/authority/receipts/custos-plan-18-task-2-schema-receipt.json"
TASK_2_V2_RECEIPT_PATH = "docs/authority/receipts/custos-plan-18-task-2-schema-receipt-v2.json"
TASK_3_RECEIPT_PATH = "docs/authority/receipts/custos-plan-18-task-3-distribution-receipt.json"
TASK_2_V2_INDEX_PATH = "docs/authority/strategy-contract-assets-v2.json"
TASK_2_V2_SCHEMA_PATH = (
    "docs/gateway-contract/v2/strategy_artifact_pre_import_verification_receipt_v1.schema.json"
)
TASK_5C_V3_INDEX_PATH = "docs/authority/strategy-contract-assets-v3.json"
TASK_5C_V3_SCHEMA_PATH = "docs/gateway-contract/v3/strategy_artifact_ref_v2.schema.json"
TASK_5C_V3_GOLDEN_PATH = "docs/authority/strategy-artifact-ref-pre-sign-golden-v3.json"
TASK_5C_V3_RECEIPT_PATH = (
    "docs/authority/receipts/custos-plan-18-task-5c-artifact-ref-v2-producer-receipt.json"
)
TASK_5D_A_V4_INDEX_PATH = "docs/authority/strategy-contract-assets-v4.json"
TASK_5D_A_V4_SCHEMA_PATH = (
    "docs/gateway-contract/v4/strategy_artifact_pre_import_verification_receipt_v2.schema.json"
)
TASK_5D_A_V4_GOLDEN_PATH = "docs/authority/strategy-artifact-pre-import-verification-golden-v4.json"
TASK_5D_A_V4_NEGATIVE_PATH = (
    "docs/authority/strategy-artifact-pre-import-verification-negative-v4.json"
)
TASK_5D_A_CONSUMER_RECEIPT_PATH = (
    "docs/authority/receipts/custos-plan-18-task-5d-a-evidence-consumer-receipt.json"
)
TASK_5D_B_COMMAND_INDEX_PATH = "docs/authority/crucible-runner-command-consumer-assets-v1.json"
TASK_5D_B_COMMAND_CONSUMER_RECEIPT_PATH = (
    "docs/authority/receipts/custos-plan-18-task-5d-b-command-consumer-receipt.json"
)
TASK_5D_B_COMMAND_CONSUMER_SOURCE = "src/custos/contracts/crucible_runner_command.py"
TASK_5D_B_CR89_CONTRACT_COMMIT = "51d23eba8aaefb30e936fc9fae1eac0e791164aa"
TASK_5D_B_CR89_PUBLICATION_COMMIT = "06b2cbc0bafc0eda2b92fc2bc3f36ba1626abc3d"
TASK_5D_B_CR89_RECEIPT_SHA256 = "105ea501b83053421066b4053ec3583e4dd109560b0689bfeb856c2f8beec5d2"
TASK_5D_B_NON_CURRENT_COMMITS = {
    "fe7be5119633c341f6e888a250a601d9db0d6e67",
    "56743f090ef3461f306d3937bfa8b054e6e7b2d8",
    "a20f7116fed35670264d3a0139974aa25daa2a26",
}
REVIEW_VENDOR_ROOT = "docs/authority/receipts/vendor"
CURRENT_STRATEGY_CONTRACT_SOURCE = (
    "packages/custos-strategy-toolkit/src/custos_toolkit/contracts/strategy_execution.py"
)
TASK_3_IMPLEMENTATION_COMMIT = "efc01da67b432e9b35beee3498415efc1bc46b98"
EXPECTED_PRODUCER = {
    "repository": "tesseract-trading/custos",
    "source_path": "src/custos/contracts/strategy_execution.py",
    "source_sha256": "71990c6a4613cb738f6a81be0cc393d79f86eeee8b36166974e4581a3ef934c3",
    "asset_index_path": "docs/authority/strategy-contract-assets-v1.json",
    "asset_index_sha256": "d87d6fc2df020e92748058c5577863b83dd6f3b2a0c0f59adbf9b9b7822dae07",
}
EXPECTED_TASK_2_RECEIPT_SHA256 = "f3c3d11b3609e644c982c82d1f3796a106a976e47e909cd94cf638b770b70e88"
EXPECTED_V2_PRODUCER_COMMIT = "f3adde2870a53a4bb52cc2a260d2c7c1c852eee2"
EXPECTED_V2_INDEX_SHA256 = "6fd49708967d59576b61529075d3423f43d936bdfac1a834ed655de0682bbcbc"
EXPECTED_V2_SCHEMA_SHA256 = "d6e21b0a9207ed8bdd6e4e21cce53070939d21e2aed1992544f9fa7f41cf3463"
EXPECTED_V2_CANDIDATE_RECEIPT_SHA256 = (
    "83005dc4090c75db8beca0fd8a825b3dc7094bc31fc99e96fb50d416c8f9f9d0"
)
EXPECTED_CONTRACT_SUMMARY = {
    "canonicalization": "sha256-canonical-json-v1",
    "execution_abi": "alephain.strategy_runtime.v1",
    "execution_abi_version": 1,
    "contract_schema_version": 1,
    "entry_point_group": "alephain.strategy_runtime.v1",
}
REVIEW_PROFILES: dict[str, dict[str, Any]] = {
    "crucible_rust_plan_88": {
        "canonical_name": (
            "Crucible Plan 88 Custos Plan 18 Task 2 requirements-only consumer review"
        ),
        "source_repository": "tesseract-trading/crucible-rust",
        "source_path": (
            "docs/authority/receipts/crucible-plan-88-custos-task-2-consumer-review.json"
        ),
        "source_commit": "9085d8deb8e78cc17a57c20ae244b48ede08799c",
        "sha256": "09bff539edafa818d1f15b866ae3626600ced90f613da68dd4e14a9385935095",
        "vendored_path": (
            "docs/authority/receipts/vendor/crucible-plan-88-custos-task-2-requirements-review.json"
        ),
        "decision_path": ("consumer_review_status",),
        "review_schema_path": ("contract_requirements", "schema_version"),
        "review_schema_value": 1,
        "producer_path": ("producer_snapshot",),
        "canonicalization_path": (
            "contract_requirements",
            "canonicalization",
            "identifier",
        ),
        "execution_abi_path": ("contract_requirements", "execution_abi"),
        "entry_point_group_path": ("contract_requirements", "entry_point", "group"),
        "assets_path": ("reviewed_assets",),
    },
    "philosophers_stone_plan_54": {
        "canonical_name": ("Philosophers-Stone Plan 54 Custos Plan 18 Task 2 requirements review"),
        "source_repository": "alchymia-labs/philosophers-stone",
        "source_path": (
            "docs/authority/receipts/ps-plan-54-custos-task-2-requirements-review.json"
        ),
        "source_commit": "7f07c090ce6d6dd4f2e11986680009a61af0934b",
        "sha256": "0a4d48c9bd1849b8a04b9a72ef6fb97942e0f66bc21b6d7916c2d5eb21650319",
        "vendored_path": (
            "docs/authority/receipts/vendor/ps-plan-54-custos-task-2-requirements-review.json"
        ),
        "decision_path": ("review_status",),
        "review_schema_path": ("schema_version",),
        "review_schema_value": "alephain.ps-plan-54-custos-task-2-requirements-review.v1",
        "producer_path": ("custos_producer_pin",),
        "canonicalization_path": ("canonicalization_contract", "identifier"),
        "execution_abi_path": ("execution_abi_contract", "identifier"),
        "entry_point_group_path": ("execution_abi_contract", "entry_point_group"),
        "assets_path": ("contract_assets",),
    },
}
V2_REVIEW_PROFILES: dict[str, dict[str, Any]] = {
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
        "decision_path": ("consumer_review_status",),
        "review_schema_path": ("receipt_schema_version",),
        "review_schema_value": 2,
        "producer_path": ("producer_snapshot",),
        "assets_path": ("reviewed_assets",),
        "candidate_receipt_path": ("producer_snapshot", "producer_receipt"),
        "candidate_status_field": "status_at_reviewed_commit",
        "false_paths": (
            ("handoff_ready",),
            ("runtime_ready",),
            ("semantic_boundary", "loaded_entry_point_property_present"),
            ("semantic_boundary", "engine_ready_property_present"),
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
        "decision_path": ("review_status",),
        "review_schema_path": ("schema_version",),
        "review_schema_value": ("alephain.ps-plan-54-custos-task-2-v2-requirements-review.v1"),
        "producer_path": ("custos_producer_pin",),
        "assets_path": ("contract_assets",),
        "candidate_receipt_path": (
            "custos_producer_pin",
            "task_2_v2_source_receipt",
        ),
        "candidate_status_field": "observed_status",
        "false_paths": (
            ("handoff_ready",),
            ("production_ready",),
            ("pre_import_contract", "loaded_entry_point_property_present"),
            ("pre_import_contract", "engine_ready_property_present"),
            ("plan_54_compatibility", "legacy_python_lane_changed"),
            ("plan_54_compatibility", "slice_gate_promoted"),
        ),
    },
}


def resolve(path: str, *, root: Path = ROOT) -> Path:
    return (root / path).resolve()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"authority JSON unreadable at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"authority JSON must be an object: {path}")
    return value


def _nested(value: object, path: tuple[str, ...]) -> object:
    current = value
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _load_gate_json(path: Path, *, label: str, errors: list[str]) -> dict[str, Any] | None:
    try:
        return load_json(path)
    except SystemExit as exc:
        errors.append(f"{label} is not valid JSON: {exc}")
        return None


def _resolve_local_file(
    value: object,
    *,
    label: str,
    root: Path,
    errors: list[str],
    required_parent: str | None = None,
) -> Path | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label} requires a non-empty repository-relative path")
        return None
    relative = Path(value)
    if relative.is_absolute():
        errors.append(f"{label} must be repository-relative")
        return None
    repository_root = root.resolve()
    path = (repository_root / relative).resolve()
    if not path.is_relative_to(repository_root):
        errors.append(f"{label} escapes the repository root")
        return None
    if required_parent is not None:
        parent = (repository_root / required_parent).resolve()
        if not path.is_relative_to(parent):
            errors.append(f"{label} must stay under {required_parent}")
            return None
    if not path.is_file():
        errors.append(f"missing {label}: {path}")
        return None
    return path


def _asset_table(
    entries: object, *, label: str, errors: list[str]
) -> dict[str, tuple[str, int]] | None:
    if not isinstance(entries, list):
        errors.append(f"{label} must be an asset list")
        return None
    result: dict[str, tuple[str, int]] = {}
    valid = True
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append(f"{label} contains a non-object asset")
            valid = False
            continue
        path = entry.get("path")
        digest = entry.get("sha256")
        size = entry.get("size_bytes")
        if not isinstance(path, str) or not re.fullmatch(r"[0-9a-f]{64}", str(digest or "")):
            errors.append(f"{label} contains an invalid path or SHA-256")
            valid = False
            continue
        if type(size) is not int or size < 0:
            errors.append(f"{label} contains an invalid size for {path}")
            valid = False
            continue
        if path in result:
            errors.append(f"{label} contains duplicate asset path {path}")
            valid = False
            continue
        result[path] = (str(digest), size)
    return result if valid else None


def _validate_contract_summary(receipt: dict[str, Any], errors: list[str]) -> None:
    summary = receipt.get("contract_summary")
    if not isinstance(summary, dict):
        errors.append("Plan 18 Task 2 receipt lacks a structured contract summary")
        return
    for field, expected in EXPECTED_CONTRACT_SUMMARY.items():
        if summary.get(field) != expected:
            errors.append(f"Plan 18 Task 2 contract summary {field} differs")


def _validate_requirement_review(
    name: str,
    slot: object,
    *,
    profile: dict[str, Any],
    receipt: dict[str, Any],
    asset_table: dict[str, tuple[str, int]],
    root: Path,
    errors: list[str],
) -> None:
    if not isinstance(slot, dict):
        errors.append(f"{name} requirements review must be a structured object")
        return
    if slot.get("status") != "ACCEPTED_REQUIREMENTS_REVIEW":
        errors.append(f"{name} requirements review decision is not accepted")
        return
    if slot.get("required_receipt_name") != profile["canonical_name"]:
        errors.append(f"{name} requirements review canonical name differs")
    evidence = slot.get("receipt")
    if not isinstance(evidence, dict):
        errors.append(f"{name} review evidence must be a structured receipt object")
        return
    for field in ("source_repository", "source_path", "source_commit", "sha256", "vendored_path"):
        if evidence.get(field) != profile[field]:
            errors.append(f"{name} review evidence {field} differs")
    vendored_path = _resolve_local_file(
        evidence.get("vendored_path"),
        label=f"{name} vendored requirements review",
        root=root,
        errors=errors,
        required_parent=REVIEW_VENDOR_ROOT,
    )
    if vendored_path is None:
        return
    actual_digest = hashlib.sha256(vendored_path.read_bytes()).hexdigest()
    if actual_digest != evidence.get("sha256"):
        errors.append(f"{name} vendored requirements review byte digest differs")
    review = _load_gate_json(vendored_path, label=f"{name} vendored review", errors=errors)
    if review is None:
        return
    if _nested(review, profile["decision_path"]) != "ACCEPTED_REQUIREMENTS_REVIEW":
        errors.append(f"{name} vendored review decision is not ACCEPTED_REQUIREMENTS_REVIEW")
    if _nested(review, profile["review_schema_path"]) != profile["review_schema_value"]:
        errors.append(f"{name} vendored review schema version differs")

    producer = receipt.get("producer")
    asset_ref = receipt.get("contract_asset_index")
    if not isinstance(producer, dict) or not isinstance(asset_ref, dict):
        errors.append(f"{name} cannot bind an invalid producer receipt")
        return
    reviewed_producer = _nested(review, profile["producer_path"])
    if not isinstance(reviewed_producer, dict):
        errors.append(f"{name} vendored review lacks a producer snapshot")
        return
    expected_commit = producer.get("commit") or producer.get("candidate_commit")
    if reviewed_producer.get("repository") != producer.get("repository"):
        errors.append(f"{name} reviewed producer repository differs")
    if reviewed_producer.get("commit") != expected_commit:
        errors.append(f"{name} reviewed producer commit differs")
    reviewed_source = reviewed_producer.get("source")
    if not isinstance(reviewed_source, dict) or reviewed_source != {
        "path": producer.get("source"),
        "sha256": producer.get("source_sha256"),
    }:
        errors.append(f"{name} reviewed producer source differs")
    reviewed_index = reviewed_producer.get("contract_asset_index")
    if not isinstance(reviewed_index, dict) or reviewed_index != {
        "path": asset_ref.get("path"),
        "sha256": asset_ref.get("sha256"),
    }:
        errors.append(f"{name} reviewed asset index differs")

    summary = receipt.get("contract_summary", {})
    if _nested(review, profile["canonicalization_path"]) != summary.get("canonicalization"):
        errors.append(f"{name} reviewed canonicalization differs")
    if _nested(review, profile["execution_abi_path"]) != summary.get("execution_abi"):
        errors.append(f"{name} reviewed execution ABI differs")
    if _nested(review, profile["entry_point_group_path"]) != summary.get("entry_point_group"):
        errors.append(f"{name} reviewed entry-point group differs")
    reviewed_assets = _asset_table(
        _nested(review, profile["assets_path"]),
        label=f"{name} reviewed assets",
        errors=errors,
    )
    if reviewed_assets is not None and reviewed_assets != asset_table:
        errors.append(f"{name} reviewed schema asset digest set differs")


def verify_strategy_contract_assets(errors: list[str]) -> None:
    index_path = resolve("docs/authority/strategy-contract-assets-v1.json")
    if not index_path.is_file():
        errors.append(f"missing strategy contract asset index: {index_path}")
        return
    index = load_json(index_path)
    for entry in index.get("assets", []):
        path = resolve(str(entry.get("path") or ""))
        if not path.is_file():
            errors.append(f"missing generated strategy contract asset: {path}")
            continue
        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_digest != entry.get("sha256"):
            errors.append(f"strategy contract asset digest differs: {path}")
        if path.stat().st_size != entry.get("size_bytes"):
            errors.append(f"strategy contract asset size differs: {path}")


def verify_plan_18_task_5c_v3_artifact_ref(errors: list[str]) -> str | None:
    """Validate the corrected producer-only pre-sign ABI without claiming handoff."""

    index_path = resolve(TASK_5C_V3_INDEX_PATH)
    receipt_path = resolve(TASK_5C_V3_RECEIPT_PATH)
    if not index_path.is_file() or not receipt_path.is_file():
        errors.append("missing Plan 18 T5c v3 ArtifactRef authority assets")
        return None
    index = load_json(index_path)
    receipt = load_json(receipt_path)
    if index.get("asset_index_schema_version") != 3:
        errors.append("Plan 18 T5c asset index schema version must be 3")
    if index.get("candidate_status") != "PRE_SIGN_ABI_ONLY":
        errors.append("Plan 18 T5c asset index status differs")
    if index.get("current_artifact_ref_type") != "StrategyArtifactRefV2":
        errors.append("Plan 18 T5c current ArtifactRef type must be V2")
    if index.get("current_artifact_ref_schema") != TASK_5C_V3_SCHEMA_PATH:
        errors.append("Plan 18 T5c current ArtifactRef schema path differs")
    for field in ("handoff_ready", "production_ready"):
        if index.get(field) is not False:
            errors.append(f"Plan 18 T5c {field} must remain false")

    legacy = index.get("legacy_non_production")
    expected_legacy = {
        "v1": {
            "asset_index": "docs/authority/strategy-contract-assets-v1.json",
            "sha256": EXPECTED_PRODUCER["asset_index_sha256"],
            "runtime_fallback_allowed": False,
        },
        "v2": {
            "asset_index": TASK_2_V2_INDEX_PATH,
            "sha256": EXPECTED_V2_INDEX_SHA256,
            "runtime_fallback_allowed": False,
        },
    }
    if legacy != expected_legacy:
        errors.append("Plan 18 T5c legacy non-production boundary differs")

    asset_table = _asset_table(index.get("assets"), label="Plan 18 T5c v3 assets", errors=errors)
    if asset_table is not None:
        for path_value, (expected_digest, expected_size) in asset_table.items():
            path = resolve(path_value)
            if not path.is_file():
                errors.append(f"missing Plan 18 T5c v3 asset: {path}")
                continue
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected_digest:
                errors.append(f"Plan 18 T5c v3 asset digest differs: {path}")
            if path.stat().st_size != expected_size:
                errors.append(f"Plan 18 T5c v3 asset size differs: {path}")

    schema_path = resolve(TASK_5C_V3_SCHEMA_PATH)
    golden_path = resolve(TASK_5C_V3_GOLDEN_PATH)
    if not schema_path.is_file() or not golden_path.is_file():
        errors.append("Plan 18 T5c current schema or golden is missing")
    else:
        schema = load_json(schema_path)
        golden = load_json(golden_path)
        allowed_fields = {
            "schema_version",
            "artifact_kind",
            "artifact_coordinate",
            "artifact_sha256",
            "artifact_size_bytes",
            "manifest_sha256",
            "manifest_size_bytes",
            "required_runtime_artifacts",
            "sbom_sha256",
            "contract_schema_sha256",
            "source_repository",
            "source_commit",
            "normalized_source_tree_sha256",
            "python_version",
            "engine",
            "engine_version",
            "base_contracts_version",
            "engine_toolkit_version",
            "build_inputs",
        }
        if schema.get("title") != "StrategyArtifactRefV2":
            errors.append("Plan 18 T5c schema title must be StrategyArtifactRefV2")
        if set(schema.get("properties", {})) != allowed_fields:
            errors.append("Plan 18 T5c ArtifactRefV2 field set differs")
        if schema.get("properties", {}).get("schema_version", {}).get("const") != 2:
            errors.append("Plan 18 T5c ArtifactRefV2 schema version must be 2")
        if set(golden.get("artifact_ref", {})) != allowed_fields:
            errors.append("Plan 18 T5c golden ArtifactRefV2 field set differs")
        if golden.get("production_handoff_ready") is not False:
            errors.append("Plan 18 T5c golden must not claim production handoff")

    source_path = resolve(str(index.get("producer_source") or ""))
    source_digest: str | None = None
    if not source_path.is_file():
        errors.append("Plan 18 T5c canonical producer source is missing")
    else:
        source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if source_digest != index.get("producer_source_sha256"):
            errors.append("Plan 18 T5c canonical producer source digest differs")

    if receipt.get("receipt_status") != "PRODUCED_AWAITING_CONSUMER_REVIEWS":
        errors.append("Plan 18 T5c producer receipt status differs")
    if receipt.get("requirements_reviews") != {}:
        errors.append("Plan 18 T5c must not fabricate consumer review receipts")
    for field in ("handoff_ready", "runtime_ready", "production_ready"):
        if receipt.get(field) is not False:
            errors.append(f"Plan 18 T5c producer receipt {field} must remain false")
    expected_index_ref = {
        "path": TASK_5C_V3_INDEX_PATH,
        "sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
    }
    if receipt.get("contract_asset_index") != expected_index_ref:
        errors.append("Plan 18 T5c producer receipt index binding differs")
    if source_digest != receipt.get("producer_source_sha256"):
        errors.append("Plan 18 T5c producer receipt source binding differs")
    return source_digest


def verify_plan_18_task_5d_a_contract_consumer(errors: list[str]) -> None:
    """Validate the exact producer assets and Custos contract-consumer receipt."""

    index_path = resolve(TASK_5D_A_V4_INDEX_PATH)
    schema_path = resolve(TASK_5D_A_V4_SCHEMA_PATH)
    golden_path = resolve(TASK_5D_A_V4_GOLDEN_PATH)
    negative_path = resolve(TASK_5D_A_V4_NEGATIVE_PATH)
    receipt_path = resolve(TASK_5D_A_CONSUMER_RECEIPT_PATH)
    required_paths = (index_path, schema_path, golden_path, negative_path, receipt_path)
    if not all(path.is_file() for path in required_paths):
        errors.append("missing Plan 18 T5d-A contract-consumer authority assets")
        return

    index = load_json(index_path)
    receipt = load_json(receipt_path)
    if index.get("status") != "READY_CONTRACT_CONSUMER_ONLY":
        errors.append("Plan 18 T5d-A v4 index status differs")
    if index.get("current_receipt_type") != "StrategyArtifactPreImportVerificationReceiptV2":
        errors.append("Plan 18 T5d-A current receipt type differs")
    if index.get("current_receipt_schema") != TASK_5D_A_V4_SCHEMA_PATH:
        errors.append("Plan 18 T5d-A current receipt schema differs")
    if index.get("contract_consumer_ready") is not True:
        errors.append("Plan 18 T5d-A contract consumer must be ready")
    for field in ("command_consumer_ready", "runtime_ready", "production_ready"):
        if index.get(field) is not False or receipt.get(field) is not False:
            errors.append(f"Plan 18 T5d-A {field} must remain false")

    source_path = resolve(str(index.get("consumer_source") or ""))
    if not source_path.is_file() or hashlib.sha256(
        source_path.read_bytes()
    ).hexdigest() != index.get("consumer_source_sha256"):
        errors.append("Plan 18 T5d-A consumer source binding differs")
    for entry in index.get("assets", []):
        path = resolve(str(entry.get("path") or ""))
        if not path.is_file():
            errors.append(f"missing Plan 18 T5d-A v4 asset: {path}")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
            errors.append(f"Plan 18 T5d-A v4 asset digest differs: {path}")
        if path.stat().st_size != entry.get("size_bytes"):
            errors.append(f"Plan 18 T5d-A v4 asset size differs: {path}")

    producer_authority = index.get("producer_authority", {})
    producer_groups = (
        producer_authority.get("philosophers_stone", {}).get("producer_assets", []),
        producer_authority.get("crucible_rust", {})
        .get("publication", {})
        .get("producer_assets", []),
    )
    for entries in producer_groups:
        for entry in entries:
            path = resolve(str(entry.get("vendored_path") or ""))
            if not path.is_file():
                errors.append(f"missing Plan 18 T5d-A producer asset: {path}")
                continue
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
                errors.append(f"Plan 18 T5d-A producer asset digest differs: {path}")
            if path.stat().st_size != entry.get("size_bytes"):
                errors.append(f"Plan 18 T5d-A producer asset size differs: {path}")

    schema = load_json(schema_path)
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
    for field, reference in expected_refs.items():
        if schema.get("properties", {}).get(field) != {"$ref": reference}:
            errors.append(f"Plan 18 T5d-A owner schema reference differs for {field}")

    for path in (golden_path, negative_path):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        sidecar = path.with_name(f"{path.name}.sha256")
        if not sidecar.is_file() or sidecar.read_text(encoding="ascii") != (
            f"{digest}  {path.name}\n"
        ):
            errors.append(f"Plan 18 T5d-A sidecar differs: {sidecar}")
    golden = load_json(golden_path)
    if golden.get("contract_consumer_ready") is not True:
        errors.append("Plan 18 T5d-A golden is not contract-consumer ready")
    for field in ("command_consumer_ready", "runtime_ready", "production_ready"):
        if golden.get(field) is not False:
            errors.append(f"Plan 18 T5d-A golden {field} must remain false")

    expected_index_binding = {
        "path": TASK_5D_A_V4_INDEX_PATH,
        "sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "size_bytes": index_path.stat().st_size,
    }
    if receipt.get("contract_asset_index") != expected_index_binding:
        errors.append("Plan 18 T5d-A consumer receipt index binding differs")
    if receipt.get("receipt_status") != "READY_CONTRACT_CONSUMER_ONLY":
        errors.append("Plan 18 T5d-A consumer receipt status differs")
    if receipt.get("contract_consumer_ready") is not True:
        errors.append("Plan 18 T5d-A consumer receipt is not ready")
    if receipt.get("policy_boundary") != {
        "crucible_local_policy_decision_reused": False,
        "runner_local_policy_decision_required": True,
    }:
        errors.append("Plan 18 T5d-A policy ownership boundary differs")
    positive = json.dumps({"schema": schema, "golden": golden, "receipt": receipt})
    for forbidden in ("release_bom_members", "verified_members"):
        if forbidden in positive:
            errors.append(f"Plan 18 T5d-A positive authority contains forbidden {forbidden}")


def verify_plan_18_task_5d_b_command_consumer(errors: list[str]) -> None:
    """Validate the sole CR89 command consumer without claiming runtime readiness."""

    index_path = resolve(TASK_5D_B_COMMAND_INDEX_PATH)
    receipt_path = resolve(TASK_5D_B_COMMAND_CONSUMER_RECEIPT_PATH)
    source_path = resolve(TASK_5D_B_COMMAND_CONSUMER_SOURCE)
    if not index_path.is_file() or not receipt_path.is_file() or not source_path.is_file():
        errors.append("missing Plan 18 T5d-B command-consumer authority assets")
        return
    index = load_json(index_path)
    receipt = load_json(receipt_path)
    if index.get("status") != "READY_COMMAND_CONSUMER_CONTRACT_ONLY":
        errors.append("Plan 18 T5d-B command asset index status differs")
    if index.get("slice_equivalence") != ["Custos Plan 18 T5d-B", "Custos Plan 19 T2"]:
        errors.append("Plan 18 T5d-B and Plan 19 T2 must remain one slice")
    if index.get("custos_publishes_command_schema") is not False:
        errors.append("Custos must not publish the Crucible runner command schema")
    for field in (
        "exact_signed_event_bytes_retained",
        "full_artifact_evidence_required",
        "acceptance_semantics_fail_closed",
        "command_contract_consumer_ready",
    ):
        if index.get(field) is not True:
            errors.append(f"Plan 18 T5d-B index {field} must be true")
    for field in ("runtime_ready", "production_ready"):
        if index.get(field) is not False or receipt.get(field) is not False:
            errors.append(f"Plan 18 T5d-B {field} must remain false")

    producer = index.get("producer_authority", {})
    if producer.get("repository") != "tesseract-trading/crucible-rust":
        errors.append("Plan 18 T5d-B producer repository differs")
    if producer.get("contract_commit") != TASK_5D_B_CR89_CONTRACT_COMMIT:
        errors.append("Plan 18 T5d-B CR89 contract commit differs")
    if producer.get("publication_commit") != TASK_5D_B_CR89_PUBLICATION_COMMIT:
        errors.append("Plan 18 T5d-B CR89 publication commit differs")
    if producer.get("producer_receipt_sha256") != TASK_5D_B_CR89_RECEIPT_SHA256:
        errors.append("Plan 18 T5d-B CR89 receipt digest differs")
    if set(producer.get("superseded_non_current_commits", [])) != (TASK_5D_B_NON_CURRENT_COMMITS):
        errors.append("Plan 18 T5d-B superseded producer set differs")

    producer_assets = producer.get("producer_assets", [])
    assets_by_source = {
        entry.get("source_path"): entry for entry in producer_assets if isinstance(entry, dict)
    }
    for entry in producer_assets:
        path = resolve(str(entry.get("vendored_path") or ""))
        if not path.is_file():
            errors.append(f"missing Plan 18 T5d-B producer asset: {path}")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
            errors.append(f"Plan 18 T5d-B producer asset digest differs: {path}")
        if path.stat().st_size != entry.get("size_bytes"):
            errors.append(f"Plan 18 T5d-B producer asset size differs: {path}")
        source_commit = entry.get("source_commit")
        if source_commit not in {
            TASK_5D_B_CR89_CONTRACT_COMMIT,
            TASK_5D_B_CR89_PUBLICATION_COMMIT,
        }:
            errors.append(f"Plan 18 T5d-B producer asset commit differs: {path}")
        source = str(entry.get("source_path") or "")
        if source.endswith(".sha256"):
            target = assets_by_source.get(source.removesuffix(".sha256"), {})
            expected_sidecar = f"{target.get('sha256', '')}\n"
            if path.read_text(encoding="ascii") != expected_sidecar:
                errors.append(f"Plan 18 T5d-B producer sidecar differs: {path}")

    producer_receipt_entry = assets_by_source.get(
        "docs/authority/receipts/crucible-plan-89-runner-command-producer-v1.json", {}
    )
    producer_receipt_path = resolve(str(producer_receipt_entry.get("vendored_path") or ""))
    if not producer_receipt_path.is_file():
        errors.append("missing Plan 18 T5d-B CR89 producer receipt")
    else:
        producer_receipt = load_json(producer_receipt_path)
        if producer_receipt.get("producer_commit") != TASK_5D_B_CR89_CONTRACT_COMMIT:
            errors.append("Plan 18 T5d-B producer receipt current commit differs")
        supersession = producer_receipt.get("supersession", {})
        if supersession.get("status") != "CURRENT":
            errors.append("Plan 18 T5d-B producer receipt must be CURRENT")
        superseded = supersession.get("supersedes", [])
        if {entry.get("commit") for entry in superseded} != TASK_5D_B_NON_CURRENT_COMMITS:
            errors.append("Plan 18 T5d-B producer receipt supersession set differs")
        if any(entry.get("status") != "NON_CURRENT" for entry in superseded):
            errors.append("Plan 18 T5d-B old producer commits must be NON_CURRENT")

    for entry in index.get("consumer_assets", []):
        path = resolve(str(entry.get("path") or ""))
        if not path.is_file():
            errors.append(f"missing Plan 18 T5d-B consumer asset: {path}")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
            errors.append(f"Plan 18 T5d-B consumer asset digest differs: {path}")
        if path.stat().st_size != entry.get("size_bytes"):
            errors.append(f"Plan 18 T5d-B consumer asset size differs: {path}")
        if str(entry.get("path") or "").startswith("docs/gateway-contract"):
            errors.append("Plan 18 T5d-B consumer assets must not publish a command schema")
    model = index.get("consumer_model", {})
    expected_source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if (
        model.get("path") != TASK_5D_B_COMMAND_CONSUMER_SOURCE
        or model.get("public_export") != "CrucibleRunnerDeploymentCommandV1"
        or model.get("sha256") != expected_source_digest
        or model.get("size_bytes") != source_path.stat().st_size
    ):
        errors.append("Plan 18 T5d-B consumer model binding differs")

    schema_entry = assets_by_source.get(
        "docs/authority/schemas/crucible-runner-deployment-command-v1.schema.json", {}
    )
    schema_path = resolve(str(schema_entry.get("vendored_path") or ""))
    golden_entry = assets_by_source.get(
        "docs/authority/golden/crucible-runner-deployment-command-v1.json", {}
    )
    golden_path = resolve(str(golden_entry.get("vendored_path") or ""))
    if schema_path.is_file():
        schema = load_json(schema_path)
        properties = schema.get("properties", {})
        if "artifact_evidence" not in properties:
            errors.append("Plan 18 T5d-B CR89 schema lacks full ArtifactEvidenceV1")
        for forbidden in ("release_bom_members", "trusted_root", "trust_policy"):
            if forbidden in properties:
                errors.append(f"Plan 18 T5d-B CR89 schema contains forbidden {forbidden}")
    if golden_path.is_file():
        golden = load_json(golden_path)
        command = golden.get("command", {})
        if not isinstance(command.get("artifact_evidence"), dict):
            errors.append("Plan 18 T5d-B golden lacks full artifact evidence")
        if golden.get("truth", {}).get("runtime_publication_enabled") is not False:
            errors.append("Plan 18 T5d-B golden must remain contract-only")

    expected_index_binding = {
        "path": TASK_5D_B_COMMAND_INDEX_PATH,
        "sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "size_bytes": index_path.stat().st_size,
    }
    if receipt.get("contract_asset_index") != expected_index_binding:
        errors.append("Plan 18 T5d-B receipt index binding differs")
    if receipt.get("receipt_status") != "READY_COMMAND_CONSUMER_CONTRACT_ONLY":
        errors.append("Plan 18 T5d-B receipt status differs")
    if receipt.get("plan_18_task_5d_b_stop") is not True:
        errors.append("Plan 18 T5d-B receipt does not close T5d-B")
    if receipt.get("plan_19_task_2_stop") is not True:
        errors.append("Plan 18 T5d-B receipt does not close Plan 19 T2")
    receipt_producer = receipt.get("crucible_producer", {})
    if (
        receipt_producer.get("contract_commit") != TASK_5D_B_CR89_CONTRACT_COMMIT
        or receipt_producer.get("publication_commit") != TASK_5D_B_CR89_PUBLICATION_COMMIT
        or receipt_producer.get("producer_receipt_sha256") != TASK_5D_B_CR89_RECEIPT_SHA256
    ):
        errors.append("Plan 18 T5d-B receipt producer binding differs")
    upstream = receipt.get("upstream_t5d_a_stop", {})
    upstream_path = resolve(str(upstream.get("path") or ""))
    if not upstream_path.is_file() or hashlib.sha256(
        upstream_path.read_bytes()
    ).hexdigest() != upstream.get("sha256"):
        errors.append("Plan 18 T5d-B upstream T5d-A STOP binding differs")


def verify_plan_18_task_2_receipt(
    errors: list[str],
    *,
    root: Path = ROOT,
    expected_producer: dict[str, Any] = EXPECTED_PRODUCER,
    review_profiles: dict[str, dict[str, Any]] = REVIEW_PROFILES,
    verify_historical_path_bytes: bool = True,
) -> None:
    receipt_path = resolve(TASK_2_RECEIPT_PATH, root=root)
    if not receipt_path.is_file():
        errors.append(f"missing Plan 18 Task 2 receipt: {receipt_path}")
        return
    receipt = load_json(receipt_path)
    if receipt.get("receipt_schema_version") != 1:
        errors.append("Plan 18 Task 2 receipt schema version must be 1")
    if receipt.get("canonical_name") != "Custos Plan 18 Task 2 schema receipt":
        errors.append("Plan 18 Task 2 receipt canonical name differs")
    _validate_contract_summary(receipt, errors)
    status = receipt.get("receipt_status")
    if status == "PENDING_REQUIREMENTS_AND_VERIFICATION":
        if receipt.get("handoff_ready") is not False:
            errors.append("pending Plan 18 Task 2 receipt must not be handoff-ready")
    elif status == "READY":
        if receipt.get("handoff_ready") is not True:
            errors.append("ready Plan 18 Task 2 receipt must be handoff-ready")
    else:
        errors.append("Plan 18 Task 2 receipt status must be pending or READY")
        return

    producer = receipt.get("producer", {})
    if not isinstance(producer, dict):
        errors.append("Plan 18 Task 2 receipt producer must be an object")
        return
    if producer.get("repository") != expected_producer["repository"]:
        errors.append("Plan 18 Task 2 producer repository differs")
    candidate_commit = producer.get("candidate_commit")
    if candidate_commit is not None and not re.fullmatch(r"[0-9a-f]{40}", str(candidate_commit)):
        errors.append("Plan 18 Task 2 producer candidate commit is invalid")
    if producer.get("source") != expected_producer["source_path"]:
        errors.append("Plan 18 Task 2 producer source path differs")
    if producer.get("source_sha256") != expected_producer["source_sha256"]:
        errors.append("Plan 18 Task 2 producer source digest differs")
    if verify_historical_path_bytes:
        source_path = _resolve_local_file(
            producer.get("source"),
            label="Plan 18 Task 2 producer source",
            root=root,
            errors=errors,
        )
        if source_path is not None:
            source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
            if source_digest != producer.get("source_sha256"):
                errors.append("Plan 18 Task 2 producer source bytes differ")

    asset_ref = receipt.get("contract_asset_index", {})
    if not isinstance(asset_ref, dict):
        errors.append("Plan 18 Task 2 contract asset index must be an object")
        return
    if asset_ref.get("path") != expected_producer["asset_index_path"]:
        errors.append("Plan 18 Task 2 asset-index path differs")
    if asset_ref.get("sha256") != expected_producer["asset_index_sha256"]:
        errors.append("Plan 18 Task 2 asset-index pinned digest differs")
    asset_path = _resolve_local_file(
        asset_ref.get("path"),
        label="Plan 18 Task 2 contract asset index",
        root=root,
        errors=errors,
    )
    asset_table: dict[str, tuple[str, int]] | None = None
    if asset_path is not None:
        asset_digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()
        if asset_digest != asset_ref.get("sha256"):
            errors.append("Plan 18 Task 2 receipt asset-index digest differs")
        index = _load_gate_json(asset_path, label="Plan 18 Task 2 asset index", errors=errors)
        if index is not None:
            asset_table = _asset_table(
                index.get("assets"),
                label="Plan 18 Task 2 asset index",
                errors=errors,
            )

    reviews = receipt.get("requirements_reviews")
    if not isinstance(reviews, dict):
        errors.append("Plan 18 Task 2 requirements reviews must be an object")
    elif asset_table is not None:
        for name, profile in review_profiles.items():
            slot = reviews.get(name)
            if status == "READY" or (
                isinstance(slot, dict) and slot.get("status") == "ACCEPTED_REQUIREMENTS_REVIEW"
            ):
                _validate_requirement_review(
                    name,
                    slot,
                    profile=profile,
                    receipt=receipt,
                    asset_table=asset_table,
                    root=root,
                    errors=errors,
                )

    if status == "READY":
        if not re.fullmatch(r"[0-9a-f]{40}", str(producer.get("commit") or "")):
            errors.append("ready Plan 18 Task 2 receipt requires an exact producer commit")
        elif producer.get("commit") != producer.get("candidate_commit"):
            errors.append("ready Plan 18 Task 2 producer commit differs from reviewed candidate")
        if producer.get("worktree_clean") is not True:
            errors.append("ready Plan 18 Task 2 receipt requires clean-worktree evidence")
        verification = receipt.get("verification", {})
        if not isinstance(verification, dict) or verification.get("status") != "PASS":
            errors.append("ready Plan 18 Task 2 receipt requires successful verification")
        elif not verification.get("executed_at") or not verification.get("environment"):
            errors.append("ready Plan 18 Task 2 receipt requires fresh verification metadata")


def _validate_v2_requirement_review(
    name: str,
    slot: object,
    *,
    profile: dict[str, Any],
    receipt: dict[str, Any],
    asset_table: dict[str, tuple[str, int]],
    root: Path,
    errors: list[str],
) -> None:
    if not isinstance(slot, dict):
        errors.append(f"{name} v2 requirements review must be a structured object")
        return
    if slot.get("status") != "ACCEPTED_REQUIREMENTS_REVIEW":
        errors.append(f"{name} v2 requirements review decision is not accepted")
    if slot.get("required_receipt_name") != profile["canonical_name"]:
        errors.append(f"{name} v2 requirements review canonical name differs")
    evidence = slot.get("receipt")
    if not isinstance(evidence, dict):
        errors.append(f"{name} v2 review evidence must be a structured receipt object")
        return
    for field in ("source_repository", "source_path", "source_commit", "sha256", "vendored_path"):
        if evidence.get(field) != profile[field]:
            errors.append(f"{name} v2 review evidence {field} differs")
    vendored_path = _resolve_local_file(
        evidence.get("vendored_path"),
        label=f"{name} vendored v2 requirements review",
        root=root,
        errors=errors,
        required_parent=REVIEW_VENDOR_ROOT,
    )
    if vendored_path is None:
        return
    if hashlib.sha256(vendored_path.read_bytes()).hexdigest() != evidence.get("sha256"):
        errors.append(f"{name} vendored v2 requirements review byte digest differs")
    review = _load_gate_json(vendored_path, label=f"{name} vendored v2 review", errors=errors)
    if review is None:
        return
    if _nested(review, profile["decision_path"]) != "ACCEPTED_REQUIREMENTS_REVIEW":
        errors.append(f"{name} vendored v2 review decision differs")
    if _nested(review, profile["review_schema_path"]) != profile["review_schema_value"]:
        errors.append(f"{name} vendored v2 review schema version differs")

    producer = receipt.get("producer")
    reviewed_producer = _nested(review, profile["producer_path"])
    if not isinstance(producer, dict) or not isinstance(reviewed_producer, dict):
        errors.append(f"{name} vendored v2 review lacks a producer snapshot")
        return
    if reviewed_producer.get("repository") != producer.get("repository"):
        errors.append(f"{name} reviewed v2 producer repository differs")
    if reviewed_producer.get("commit") != producer.get("candidate_commit"):
        errors.append(f"{name} reviewed v2 producer commit differs")
    reviewed_index = reviewed_producer.get("contract_asset_index")
    index_ref = receipt.get("contract_asset_index")
    if not isinstance(reviewed_index, dict) or not isinstance(index_ref, dict):
        errors.append(f"{name} reviewed v2 asset index is missing")
    elif any(reviewed_index.get(field) != index_ref.get(field) for field in ("path", "sha256")):
        errors.append(f"{name} reviewed v2 asset index differs")
    reviewed_schema = reviewed_producer.get("pre_import_receipt_schema")
    schema_ref = receipt.get("pre_import_receipt_schema")
    if not isinstance(reviewed_schema, dict) or not isinstance(schema_ref, dict):
        errors.append(f"{name} reviewed pre-import schema is missing")
    elif any(reviewed_schema.get(field) != schema_ref.get(field) for field in ("path", "sha256")):
        errors.append(f"{name} reviewed pre-import schema differs")

    candidate = _nested(review, profile["candidate_receipt_path"])
    if not isinstance(candidate, dict):
        errors.append(f"{name} reviewed candidate receipt snapshot is missing")
    else:
        if candidate.get("path") != TASK_2_V2_RECEIPT_PATH:
            errors.append(f"{name} reviewed candidate receipt path differs")
        if candidate.get("sha256") != EXPECTED_V2_CANDIDATE_RECEIPT_SHA256:
            errors.append(f"{name} reviewed candidate receipt digest differs")
        if candidate.get(profile["candidate_status_field"]) != "PENDING_REQUIREMENTS_REVIEWS":
            errors.append(f"{name} reviewed candidate receipt status differs")
    for false_path in profile["false_paths"]:
        if _nested(review, false_path) is not False:
            errors.append(f"{name} v2 review false boundary differs at {'.'.join(false_path)}")

    v1_preservation = review.get("v1_byte_preservation")
    if not isinstance(v1_preservation, dict):
        errors.append(f"{name} v2 review lacks v1 byte-preservation evidence")
    elif (
        v1_preservation.get("canonical_v1_paths_changed") != []
        or v1_preservation.get("v2_index_declares_v1_canonical_replaced") is not False
        or v1_preservation.get("asset_index_sha256_before_and_after")
        != EXPECTED_PRODUCER["asset_index_sha256"]
        or v1_preservation.get("ready_receipt_sha256_before_and_after")
        != EXPECTED_TASK_2_RECEIPT_SHA256
    ):
        errors.append(f"{name} v2 review v1 byte-preservation evidence differs")
    reviewed_assets = _asset_table(
        _nested(review, profile["assets_path"]),
        label=f"{name} reviewed v2 assets",
        errors=errors,
    )
    if reviewed_assets is not None and reviewed_assets != asset_table:
        errors.append(f"{name} reviewed v2 asset digest set differs")


def verify_plan_18_task_2_v2_candidate(errors: list[str], *, root: Path = ROOT) -> str | None:
    """Validate reviewed T5a intake without claiming T5b/runtime readiness."""

    initial_error_count = len(errors)
    receipt_path = resolve(TASK_2_V2_RECEIPT_PATH, root=root)
    if not receipt_path.is_file():
        errors.append(f"missing Plan 18 Task 2 v2 candidate receipt: {receipt_path}")
        return None
    receipt = load_json(receipt_path)
    if receipt.get("receipt_status") != "READY_PRE_IMPORT_VERIFIER":
        errors.append("Plan 18 Task 2 v2 scoped handoff status differs")
    if receipt.get("requirements_review_status") != "ACCEPTED":
        errors.append("Plan 18 Task 2 v2 requirements-review decision differs")
    if receipt.get("handoff_ready") is not True:
        errors.append("Plan 18 Task 2 v2 scoped handoff must be ready")
    for field in (
        "loaded",
        "engine_ready",
        "runtime_ready",
        "production_ready",
        "immutable_toolkit_rc_ready",
    ):
        if receipt.get(field) is not False:
            errors.append(f"Plan 18 Task 2 v2 {field} must remain false")

    expected_predecessor = {
        "asset_index": {
            "path": EXPECTED_PRODUCER["asset_index_path"],
            "sha256": EXPECTED_PRODUCER["asset_index_sha256"],
        },
        "task_2_receipt": {
            "path": TASK_2_RECEIPT_PATH,
            "sha256": EXPECTED_TASK_2_RECEIPT_SHA256,
        },
    }
    if receipt.get("predecessor") != expected_predecessor:
        errors.append("Plan 18 Task 2 v2 predecessor binding differs")
    for predecessor in expected_predecessor.values():
        path = resolve(predecessor["path"], root=root)
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != predecessor["sha256"]
        ):
            errors.append(f"Plan 18 Task 2 v2 predecessor bytes differ: {path}")

    producer = receipt.get("producer")
    source_digest: str | None = None
    if not isinstance(producer, dict):
        errors.append("Plan 18 Task 2 v2 producer must be an object")
    else:
        if producer.get("candidate_commit") != EXPECTED_V2_PRODUCER_COMMIT:
            errors.append("Plan 18 Task 2 v2 candidate commit differs")
        if producer.get("worktree_clean") is not True:
            errors.append("Plan 18 Task 2 v2 candidate clean-worktree evidence differs")
        if producer.get("source") != CURRENT_STRATEGY_CONTRACT_SOURCE:
            errors.append("Plan 18 Task 2 v2 canonical source path differs")
        source_digest = producer.get("source_sha256")
        if not isinstance(source_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", source_digest):
            errors.append("Plan 18 Task 2 v2 historical source digest is invalid")

    reviewed_candidate = receipt.get("reviewed_candidate_receipt")
    expected_candidate = {
        "commit": EXPECTED_V2_PRODUCER_COMMIT,
        "path": TASK_2_V2_RECEIPT_PATH,
        "sha256": EXPECTED_V2_CANDIDATE_RECEIPT_SHA256,
        "receipt_status": "PENDING_REQUIREMENTS_REVIEWS",
        "handoff_ready": False,
        "production_ready": False,
    }
    if reviewed_candidate != expected_candidate:
        errors.append("Plan 18 Task 2 v2 reviewed candidate receipt binding differs")
    expected_t5b_evidence = {
        "commit": "560e9f5b80962df3307f855be7ceef70c3585bd7",
        "focused_tests_passed": 49,
        "production_pre_import_verifier_library_implemented": True,
        "public_pre_import_receipt_library_emission_implemented": True,
        "runtime_invocation_caller_wired": False,
        "strategy_import_wired": False,
        "current_head_full_make_verify_passed": True,
        "verification_head": "a856455d33b5defd05284183023db6d4320f8101",
    }
    if receipt.get("t5b_implementation_evidence") != expected_t5b_evidence:
        errors.append("Plan 18 Task 2 v2 T5b partial implementation evidence differs")

    index_asset_table: dict[str, tuple[str, int]] | None = None
    index_ref = receipt.get("contract_asset_index")
    if not isinstance(index_ref, dict) or index_ref != {
        "path": TASK_2_V2_INDEX_PATH,
        "sha256": EXPECTED_V2_INDEX_SHA256,
    }:
        errors.append("Plan 18 Task 2 v2 asset index reference differs")
    else:
        index_path = _resolve_local_file(
            index_ref.get("path"),
            label="Plan 18 Task 2 v2 asset index",
            root=root,
            errors=errors,
        )
        if index_path is not None:
            if hashlib.sha256(index_path.read_bytes()).hexdigest() != EXPECTED_V2_INDEX_SHA256:
                errors.append("Plan 18 Task 2 v2 asset index digest differs")
            index = _load_gate_json(
                index_path, label="Plan 18 Task 2 v2 asset index", errors=errors
            )
            if index is not None:
                if (
                    index.get("candidate_status") != "PENDING_REQUIREMENTS_REVIEWS"
                    or index.get("v1_canonical_replaced") is not False
                    or index.get("predecessor") != expected_predecessor
                ):
                    errors.append("Plan 18 Task 2 v2 asset index candidate boundary differs")
                if (
                    source_digest is not None
                    and index.get("producer_source_sha256") != source_digest
                ):
                    errors.append("Plan 18 Task 2 v2 index source digest differs")
                index_asset_table = _asset_table(
                    index.get("assets"),
                    label="Plan 18 Task 2 v2 asset index",
                    errors=errors,
                )
                for entry in index.get("assets", []):
                    if not isinstance(entry, dict):
                        continue
                    asset_path = _resolve_local_file(
                        entry.get("path"),
                        label="Plan 18 Task 2 v2 generated asset",
                        root=root,
                        errors=errors,
                    )
                    if asset_path is None:
                        continue
                    if hashlib.sha256(asset_path.read_bytes()).hexdigest() != entry.get("sha256"):
                        errors.append(f"Plan 18 Task 2 v2 asset digest differs: {asset_path}")
                    if asset_path.stat().st_size != entry.get("size_bytes"):
                        errors.append(f"Plan 18 Task 2 v2 asset size differs: {asset_path}")

    schema_ref = receipt.get("pre_import_receipt_schema")
    if not isinstance(schema_ref, dict) or schema_ref != {
        "path": TASK_2_V2_SCHEMA_PATH,
        "sha256": EXPECTED_V2_SCHEMA_SHA256,
    }:
        errors.append("Plan 18 Task 2 v2 pre-import schema reference differs")

    reviews = receipt.get("requirements_reviews")
    if not isinstance(reviews, dict) or set(reviews) != set(V2_REVIEW_PROFILES):
        errors.append("Plan 18 Task 2 v2 accepted requirements review set differs")
    elif index_asset_table is not None:
        for name, profile in V2_REVIEW_PROFILES.items():
            _validate_v2_requirement_review(
                name,
                reviews[name],
                profile=profile,
                receipt=receipt,
                asset_table=index_asset_table,
                root=root,
                errors=errors,
            )

    expected_verification = {
        "status": "PASS",
        "command": "make verify",
        "exact_head": "a856455d33b5defd05284183023db6d4320f8101",
        "worktree_clean": True,
        "tests": {"passed": 528, "skipped": 4, "xfailed": 1},
        "formatted_files": 169,
        "ruff": "PASS",
        "generator": "PASS",
        "authority": "PASS",
        "extraction": {"verified": 241, "total": 241},
        "strict_mypy": {
            "base": {"errors": 0, "modules": 40},
            "adapter": {"errors": 0, "modules": 59},
        },
    }
    if receipt.get("verification") != expected_verification:
        errors.append("Plan 18 Task 2 v2 exact-HEAD verification evidence differs")
    expected_blockers: list[str] = []
    if receipt.get("open_blockers") != expected_blockers:
        errors.append("Plan 18 Task 2 v2 open blocker set differs")
    expected_scoped_handoff = {
        "status": "READY_PRE_IMPORT_VERIFIER",
        "includes": [
            "exact pre-import contract schema and candidate assets",
            "accepted Crucible and Philosophers-Stone requirements reviews",
            "production pre-import verifier library and typed receipt return",
        ],
        "excludes": [
            "runtime invocation caller",
            "strategy import or loaded entry point",
            "engine readiness and runtime lifecycle",
            "immutable toolkit RC",
            "runtime or production readiness",
        ],
    }
    if receipt.get("scoped_handoff") != expected_scoped_handoff:
        errors.append("Plan 18 Task 2 v2 scoped handoff boundary differs")
    if receipt.get("deferred_to_plan_19") != [
        "runtime invocation caller",
        "strategy import and loaded entry point",
        "engine readiness and runtime lifecycle",
    ]:
        errors.append("Plan 18 Task 2 v2 Plan 19 deferral differs")
    if receipt.get("downstream_open_work") != [
        "Custos Plan 18 Task 6 immutable toolkit RC receipt"
    ]:
        errors.append("Plan 18 Task 2 v2 downstream work boundary differs")
    if len(errors) != initial_error_count:
        return None
    return source_digest


def verify_plan_18_task_3_distribution_receipt(
    errors: list[str],
    *,
    root: Path = ROOT,
    allowed_current_source_digest: str | None = None,
) -> bool:
    """Validate the explicit T3 successor path without rewriting Task 2 history."""

    initial_error_count = len(errors)
    receipt_path = resolve(TASK_3_RECEIPT_PATH, root=root)
    if not receipt_path.is_file():
        errors.append(f"missing Plan 18 Task 3 distribution receipt: {receipt_path}")
        return False
    receipt = load_json(receipt_path)
    if receipt.get("receipt_schema_version") != 1:
        errors.append("Plan 18 Task 3 receipt schema version must be 1")
    if receipt.get("receipt_status") != "READY":
        errors.append("Plan 18 Task 3 receipt must be READY")
    if receipt.get("handoff_ready") is not True:
        errors.append("Plan 18 Task 3 READY receipt must be handoff-ready")
    if receipt.get("implementation") != {
        "repository": "tesseract-trading/custos",
        "commit": TASK_3_IMPLEMENTATION_COMMIT,
    }:
        errors.append("Plan 18 Task 3 implementation commit binding differs")
    verification = receipt.get("verification")
    if not isinstance(verification, dict) or verification.get("status") != "PASS":
        errors.append("Plan 18 Task 3 receipt requires successful verification evidence")
    elif not verification.get("executed_at") or verification.get("environment") != {
        "checkout_head": TASK_3_IMPLEMENTATION_COMMIT,
        "worktree_clean": True,
    }:
        errors.append("Plan 18 Task 3 receipt requires clean exact-HEAD verification evidence")
    else:
        expected_commands = [
            "uv run pytest tests/test_toolkit_distribution.py tests/test_toolkit_contracts.py tests/test_plan18_task2_receipt.py -q",
            "make check",
            "make check-authority",
            "make toolkit-typecheck",
        ]
        if verification.get("required_commands") != expected_commands:
            errors.append("Plan 18 Task 3 verification command set differs")
    if receipt.get("canonical_move_active") is not True:
        errors.append("Plan 18 Task 3 canonical source move is not active")

    historical = receipt.get("historical_task_2_source")
    if historical != {
        "path": EXPECTED_PRODUCER["source_path"],
        "producer_commit": "b36e9edf3ce9d2080e0d77b22ae99a65e32aaaf0",
        "sha256": EXPECTED_PRODUCER["source_sha256"],
    }:
        errors.append("Plan 18 Task 3 historical Task 2 source binding differs")

    current = receipt.get("current_canonical_source")
    if not isinstance(current, dict) or current.get("path") != CURRENT_STRATEGY_CONTRACT_SOURCE:
        errors.append("Plan 18 Task 3 current canonical source path differs")
    else:
        canonical_path = _resolve_local_file(
            current.get("path"),
            label="Plan 18 Task 3 canonical contract source",
            root=root,
            errors=errors,
        )
        if current.get("sha256") != EXPECTED_PRODUCER["source_sha256"]:
            errors.append("Plan 18 Task 3 canonical source digest binding differs")
        elif canonical_path is not None:
            digest = hashlib.sha256(canonical_path.read_bytes()).hexdigest()
            if digest not in {current.get("sha256"), allowed_current_source_digest}:
                errors.append("Plan 18 Task 3 canonical source bytes differ")

    shim = receipt.get("legacy_shim")
    if not isinstance(shim, dict) or shim.get("contains_implementation") is not False:
        errors.append("Plan 18 Task 3 legacy source is not declared as a pure shim")
    else:
        shim_path = _resolve_local_file(
            shim.get("path"),
            label="Plan 18 Task 3 legacy contract shim",
            root=root,
            errors=errors,
        )
        if shim_path is not None:
            shim_bytes = shim_path.read_bytes()
            if hashlib.sha256(shim_bytes).hexdigest() == EXPECTED_PRODUCER["source_sha256"]:
                errors.append("Plan 18 Task 3 legacy shim still contains canonical source bytes")
            if b"custos_toolkit.contracts.strategy_execution" not in shim_bytes:
                errors.append("Plan 18 Task 3 legacy shim does not re-export canonical contracts")

    expected_distributions = {
        "base": {
            "name": "custos-strategy-toolkit",
            "version": "0.1.0",
            "requires_python": ">=3.11",
        },
        "nautilus": {
            "name": "custos-strategy-toolkit-nautilus",
            "version": "0.1.0",
            "requires_python": ">=3.12,<3.13",
            "base_requirement": "custos-strategy-toolkit==0.1.0",
            "engine_requirement": "nautilus-trader==1.230.0",
        },
    }
    if receipt.get("distributions") != expected_distributions:
        errors.append("Plan 18 Task 3 distribution metadata differs")
    return len(errors) == initial_error_count


def verify_plan_18_task_6_release_readiness(manifest: dict[str, object], errors: list[str]) -> None:
    expected_entries = (
        {
            "role": "toolkit_rc_t6d_pending_receipt_schema_v1_contract_only",
            "path": ("docs/gateway-contract/v1/toolkit_rc_t6d_pending_receipt_v1.schema.json"),
            "contract_only": True,
            "ready_receipt_published": False,
        },
        {
            "role": "toolkit_rc_authority_receipt_schema_v1",
            "path": "docs/gateway-contract/v1/toolkit_rc_authority_receipt_v1.schema.json",
            "contract_only": True,
            "stable_ready_path": (
                "docs/authority/receipts/custos-plan-18-task-6-toolkit-rc-receipt.json"
            ),
            "receipt_present": False,
            "receipt_status": "PENDING_T6E_EXTERNAL_RELEASE",
            "ready_receipt_published": False,
        },
        {
            "role": "toolkit_rc_t6e_promotion_runner",
            "path": "scripts/toolkit_rc_promote.py",
            "contract_only": True,
            "ready_receipt_published": False,
        },
        {
            "role": "toolkit_rc_t6d_release_readiness_runner",
            "path": "scripts/toolkit_rc_release_readiness.py",
            "contract_only": True,
            "ready_receipt_published": False,
        },
        {
            "role": "toolkit_rc_t6d_production_release_workflow",
            "path": ".github/workflows/release-toolkit-rc.yml",
            "contract_only": True,
            "ready_receipt_published": False,
        },
    )
    entries = manifest.get("authority_documents", [])
    for entry in expected_entries:
        if entry not in entries:
            errors.append(f"authority manifest lacks T6d contract-only entry {entry['role']}")

    pending_schema_path = resolve(
        "docs/gateway-contract/v1/toolkit_rc_t6d_pending_receipt_v1.schema.json"
    )
    if pending_schema_path.is_file():
        pending_schema = load_json(pending_schema_path)
        properties = pending_schema.get("properties", {})
        expected_constants = {
            "status": "PENDING_T6D_RELEASE_RUNNER",
            "ready": False,
            "production_credentials_used": False,
            "production_signature_verified": False,
            "remote_publication_verified": False,
            "final_receipt_published": False,
        }
        for name, value in expected_constants.items():
            if not isinstance(properties.get(name), dict) or (
                properties[name].get("const") != value
            ):
                errors.append(f"T6d pending schema does not fail closed for {name}")

    manifest_schema_path = resolve(
        "docs/gateway-contract/v1/toolkit_rc_receipt_manifest_v1.schema.json"
    )
    if manifest_schema_path.is_file():
        manifest_schema = load_json(manifest_schema_path)
        member_properties = (
            manifest_schema.get("$defs", {}).get("ToolkitRcMemberV1", {}).get("properties", {})
        )
        required_bindings = {
            "t4_zero_rewrite_receipt",
            "t4b_typing_closure_receipt",
            "dependency_lock_evidence",
            "slsa_provenance",
        }
        if not required_bindings.issubset(member_properties):
            errors.append("T6a manifest schema lacks corrected T4/T4b/T6d bindings")
        if "t4b_zero_rewrite_receipt" in member_properties:
            errors.append("T6a manifest schema retains obsolete T4b zero-rewrite alias")

    workflow_path = resolve(".github/workflows/release-toolkit-rc.yml")
    if workflow_path.is_file():
        workflow = workflow_path.read_text(encoding="utf-8")
        required_phrases = (
            "workflow_dispatch:",
            "permissions:\n  contents: read\n  id-token: write",
            "environment: toolkit-rc-release",
            (
                "https://github.com/alchymia-labs/custos/.github/workflows/"
                "release-toolkit-rc.yml@refs/heads/main"
            ),
            "sigstore sign --bundle",
            "sigstore verify identity",
            "--production-release-runner",
            "group: toolkit-rc-${{ inputs.candidate_version }}",
            "durable_receipt_url=${{ steps.publish.outputs.durable_receipt_url }}",
        )
        for phrase in required_phrases:
            if phrase not in workflow:
                errors.append(f"T6d production workflow lacks {phrase!r}")
        for forbidden in (
            "packages: write",
            "contents: write",
            "actions/upload-artifact",
            "softprops/action-gh-release",
            "skip-existing",
        ):
            if forbidden in workflow:
                errors.append(f"T6d production workflow contains forbidden {forbidden!r}")

    verify_plan_18_task_6_release_authority(manifest, errors)


def verify_plan_18_task_6_release_authority(manifest: dict[str, object], errors: list[str]) -> None:
    ready_path = resolve("docs/authority/receipts/custos-plan-18-task-6-toolkit-rc-receipt.json")
    ecosystem_path = resolve("docs/authority/ecosystem-authority.json")
    ecosystem = load_json(ecosystem_path) if ecosystem_path.is_file() else {}
    release = ecosystem.get("toolkit_rc_release", {})
    if not isinstance(release, dict):
        errors.append("ecosystem authority lacks toolkit_rc_release state")
        return
    if not ready_path.exists():
        if (
            release.get("receipt_status") != "PENDING_T6E_EXTERNAL_RELEASE"
            or release.get("receipt_present") is not False
            or release.get("handoff_ready") is not False
        ):
            errors.append("T6e manifest/ecosystem PENDING state differs")
        return
    ready = load_json(ready_path)
    required_ready = {
        "status": "READY_TOOLKIT_RC",
        "ready": True,
        "handoff_ready": True,
        "production_credentials_used": True,
        "production_signature_verified": True,
        "remote_publication_verified": True,
        "authority_registered": True,
        "runtime_ready": False,
        "production_ready": False,
        "strategy_release_bom_created": False,
    }
    for name, value in required_ready.items():
        if ready.get(name) != value:
            errors.append(f"T6e READY authority differs for {name}")
    if ready.get("final_blockers") != []:
        errors.append("T6e READY authority retains final blockers")
    ready_sha256 = hashlib.sha256(ready_path.read_bytes()).hexdigest()
    ready_entries = [
        entry
        for entry in manifest.get("authority_documents", [])
        if entry.get("role") == "plan_18_task_6_toolkit_rc_ready_receipt"
    ]
    if len(ready_entries) != 1 or ready_entries[0].get("sha256") != ready_sha256:
        errors.append("T6e READY receipt manifest registration differs")
    if (
        release.get("receipt_status") != "READY_TOOLKIT_RC"
        or release.get("receipt_present") is not True
        or release.get("handoff_ready") is not True
        or release.get("receipt_sha256") != ready_sha256
    ):
        errors.append("T6e READY receipt ecosystem registration differs")


def main() -> int:
    manifest = load_json(MANIFEST_PATH)
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("authority manifest schema_version must be 1")
    for entry in manifest.get("authority_documents", []):
        path = resolve(entry["path"])
        if not path.is_file():
            errors.append(f"missing {entry['role']}: {path}")
    verify_plan_18_task_6_release_readiness(manifest, errors)
    snapshot_path = resolve("docs/authority/ecosystem-authority.json")
    if snapshot_path.is_file():
        snapshot = load_json(snapshot_path)
        if snapshot.get("migration_heads") != manifest.get("expected_migration_heads"):
            errors.append("authority snapshot migration heads differ from manifest")
        fixture = snapshot.get("runner_command_golden_fixture")
        if not isinstance(fixture, dict):
            errors.append("authority snapshot lacks runner command golden fixture")
        else:
            fixture_path = resolve(str(fixture.get("path") or ""))
            if not fixture_path.is_file():
                errors.append(f"missing runner command golden fixture: {fixture_path}")
            else:
                fixture_bytes = fixture_path.read_bytes()
                actual_digest = hashlib.sha256(fixture_bytes).hexdigest()
                if actual_digest != fixture.get("sha256"):
                    errors.append("runner command golden fixture sha256 differs from snapshot")
                sidecar_path = resolve(str(fixture.get("sha256_sidecar") or ""))
                expected_sidecar = f"{actual_digest}  {fixture_path.name}\n"
                if not sidecar_path.is_file():
                    errors.append(f"missing runner command golden sidecar: {sidecar_path}")
                elif sidecar_path.read_text(encoding="ascii") != expected_sidecar:
                    errors.append("runner command golden sidecar differs from fixture")
                sibling_value = fixture.get("optional_sibling_path")
                if isinstance(sibling_value, str) and sibling_value:
                    sibling_path = resolve(sibling_value)
                    if sibling_path.is_file() and sibling_path.read_bytes() != fixture_bytes:
                        errors.append(
                            f"runner command golden differs from optional sibling: {sibling_path}"
                        )
    verify_strategy_contract_assets(errors)
    verify_plan_18_task_2_v2_candidate(errors)
    current_source_digest = verify_plan_18_task_5c_v3_artifact_ref(errors)
    verify_plan_18_task_5d_a_contract_consumer(errors)
    verify_plan_18_task_5d_b_command_consumer(errors)
    task_3_move_verified = verify_plan_18_task_3_distribution_receipt(
        errors,
        allowed_current_source_digest=current_source_digest,
    )
    verify_plan_18_task_2_receipt(
        errors,
        verify_historical_path_bytes=not task_3_move_verified,
    )
    for entry in manifest.get("external_optional_documents", []):
        path = resolve(entry["path"])
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for phrase in entry.get("must_contain", []):
            if phrase not in text:
                errors.append(f"optional workspace authority {path} lacks {phrase!r}")
    drift = manifest.get("doc_drift", {})
    patterns = [re.compile(value, re.IGNORECASE) for value in drift.get("forbidden_regex", [])]
    for value in drift.get("paths", []):
        path = resolve(value)
        if not path.is_file():
            errors.append(f"missing drift-scanned file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                errors.append(f"forbidden topology residue in {path}: {match.group(0)!r}")
    for claim in manifest.get("required_claims", []):
        path = resolve(claim["path"])
        if not path.is_file():
            errors.append(f"missing required-claim file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        for phrase in claim.get("must_contain", []):
            if phrase not in text:
                errors.append(f"{path} lacks required claim {phrase!r}")
    if errors:
        print("authority gate failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("authority gate passed for standalone custos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
