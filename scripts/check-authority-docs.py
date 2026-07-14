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
TASK_3_RECEIPT_PATH = "docs/authority/receipts/custos-plan-18-task-3-distribution-receipt.json"
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


def verify_plan_18_task_3_distribution_receipt(errors: list[str], *, root: Path = ROOT) -> bool:
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
            if digest != current.get("sha256"):
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


def main() -> int:
    manifest = load_json(MANIFEST_PATH)
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("authority manifest schema_version must be 1")
    for entry in manifest.get("authority_documents", []):
        path = resolve(entry["path"])
        if not path.is_file():
            errors.append(f"missing {entry['role']}: {path}")
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
    task_3_move_verified = verify_plan_18_task_3_distribution_receipt(errors)
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
