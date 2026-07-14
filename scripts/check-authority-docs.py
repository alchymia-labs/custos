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
