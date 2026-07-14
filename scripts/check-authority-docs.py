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


def resolve(path: str) -> Path:
    return (ROOT / path).resolve()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"authority JSON unreadable at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"authority JSON must be an object: {path}")
    return value


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


def verify_plan_18_task_2_receipt(errors: list[str]) -> None:
    receipt_path = resolve("docs/authority/receipts/custos-plan-18-task-2-schema-receipt.json")
    if not receipt_path.is_file():
        errors.append(f"missing Plan 18 Task 2 receipt: {receipt_path}")
        return
    receipt = load_json(receipt_path)
    status = receipt.get("receipt_status")
    if status == "PENDING_REQUIREMENTS_AND_VERIFICATION":
        if receipt.get("handoff_ready") is not False:
            errors.append("pending Plan 18 Task 2 receipt must not be handoff-ready")
        return
    if status != "READY":
        errors.append("Plan 18 Task 2 receipt status must be pending or READY")
        return
    producer = receipt.get("producer", {})
    if not re.fullmatch(r"[0-9a-f]{40}", str(producer.get("commit") or "")):
        errors.append("ready Plan 18 Task 2 receipt requires an exact producer commit")
    if producer.get("worktree_clean") is not True:
        errors.append("ready Plan 18 Task 2 receipt requires clean-worktree evidence")
    reviews = receipt.get("requirements_reviews", {})
    expected_reviews = {
        "crucible_rust_plan_88": "ACCEPTED",
        "philosophers_stone_plan_54": "ACCEPTED",
    }
    for name, expected in expected_reviews.items():
        review = reviews.get(name, {})
        if review.get("status") != expected or not review.get("receipt"):
            errors.append(f"ready Plan 18 Task 2 receipt lacks accepted {name} evidence")
    verification = receipt.get("verification", {})
    if verification.get("status") != "PASS" or not verification.get("executed_at"):
        errors.append("ready Plan 18 Task 2 receipt requires fresh authority verification")
    asset_ref = receipt.get("contract_asset_index", {})
    asset_path = resolve(str(asset_ref.get("path") or ""))
    if not asset_path.is_file():
        errors.append("ready Plan 18 Task 2 receipt references a missing asset index")
    elif hashlib.sha256(asset_path.read_bytes()).hexdigest() != asset_ref.get("sha256"):
        errors.append("ready Plan 18 Task 2 receipt asset-index digest differs")


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
    verify_plan_18_task_2_receipt(errors)
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
