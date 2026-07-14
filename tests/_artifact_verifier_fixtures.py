from __future__ import annotations

import base64
import copy
import csv
import hashlib
import io
import json
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from custos_toolkit.contracts.strategy_execution import (
    StrategyExecutionCommandBindingV1,
    canonical_json_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE_GOLDEN = ROOT / "docs/authority/strategy-artifact-lifecycle-golden-v1.json"


@dataclass(frozen=True, slots=True)
class ArtifactFixture:
    command: StrategyExecutionCommandBindingV1
    bom_bytes: bytes
    member_paths: dict[str, Path]
    manifest_bytes: bytes


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _record_hash(payload: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode()
    return f"sha256={digest}"


def regular_zip_info(name: str, *, compress_type: int = zipfile.ZIP_STORED) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = compress_type
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def write_test_wheel(
    path: Path,
    *,
    extra_entries: list[tuple[zipfile.ZipInfo, bytes]] | None = None,
    module_payload: bytes = b"class RuntimeAdapter:\n    pass\n",
    entry_point: str = "strategies.supertrend:RuntimeAdapter",
    entry_point_group: str = "alephain.strategy_runtime.v1",
    record_digest_override: str | None = None,
    compression: int = zipfile.ZIP_STORED,
) -> None:
    dist_info = "supertrend-1.0.0.dist-info"
    entries: list[tuple[zipfile.ZipInfo, bytes]] = [
        (regular_zip_info("strategies/__init__.py", compress_type=compression), b""),
        (
            regular_zip_info("strategies/supertrend.py", compress_type=compression),
            module_payload,
        ),
        (
            regular_zip_info(f"{dist_info}/entry_points.txt", compress_type=compression),
            (f"[{entry_point_group}]\nsupertrend = {entry_point}\n").encode(),
        ),
        (
            regular_zip_info(f"{dist_info}/WHEEL", compress_type=compression),
            b"Wheel-Version: 1.0\nGenerator: custos-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        ),
        (
            regular_zip_info(f"{dist_info}/METADATA", compress_type=compression),
            b"Metadata-Version: 2.3\nName: supertrend\nVersion: 1.0.0\n",
        ),
    ]
    entries.extend(extra_entries or [])

    record_rows: list[list[str]] = []
    for info, payload in entries:
        digest = record_digest_override or _record_hash(payload)
        record_rows.append([info.filename, digest, str(len(payload))])
    record_name = f"{dist_info}/RECORD"
    record_rows.append([record_name, "", ""])
    record_stream = io.StringIO(newline="")
    csv.writer(record_stream, lineterminator="\n").writerows(record_rows)
    entries.append((regular_zip_info(record_name), record_stream.getvalue().encode()))

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for info, payload in entries:
            archive.writestr(info, payload)


def build_artifact_fixture(
    tmp_path: Path,
    *,
    trust_policy_digest: str = "4" * 64,
    trust_policy_id: str = "custos-strategy-release",
    trust_policy_version: int = 1,
) -> ArtifactFixture:
    golden = json.loads(LIFECYCLE_GOLDEN.read_text(encoding="utf-8"))
    command_data: dict[str, Any] = copy.deepcopy(
        golden["signed_command"]["strategy_artifact_binding"]
    )
    members: list[dict[str, Any]] = command_data["release_bom_members"]

    runtime_members = [member for member in members if member["role"] == "runtime_artifact"]
    manifest_data = {
        "schema_version": 1,
        "execution_abi": "alephain.strategy_runtime.v1",
        "entry_point_group": "alephain.strategy_runtime.v1",
        "entry_point": "strategies.supertrend:RuntimeAdapter",
        "engine": "nautilus",
        "engine_version": "1.230.0",
        "requires_python": ">=3.12,<3.13",
        "base_contracts_version": "1.0.0rc1",
        "engine_toolkit_version": "1.0.0rc1",
        "config_schema_sha256": "a" * 64,
        "runtime_artifacts": runtime_members,
    }
    manifest_bytes = canonical_json_bytes(manifest_data)

    member_root = tmp_path / "members"
    member_paths: dict[str, Path] = {}
    role_payloads: dict[str, bytes] = {
        "strategy_manifest": manifest_bytes,
        "attestation_bundle": b'{"mediaType":"application/vnd.dev.sigstore.bundle+json"}',
        "sbom": b'{"spdxVersion":"SPDX-2.3"}',
        "contract_schema": b'{"schema":"strategy-contract-assets-v1"}',
        "source_tree": b"normalized-source-tree-v1\n",
        "runtime_artifact": b'{"type":"object","additionalProperties":false}',
        "base_contracts_wheel": b"base-contracts-wheel",
        "nautilus_wheel": b"nautilus-toolkit-wheel",
    }

    for member in members:
        path = member_root / member["name"]
        if member["role"] == "strategy_wheel":
            write_test_wheel(path)
            payload = path.read_bytes()
        else:
            payload = role_payloads[member["role"]]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        member["size_bytes"] = len(payload)
        member["sha256"] = sha256_hex(payload)
        member_paths[member["name"]] = path

    by_role = {member["role"]: member for member in members}
    artifact_ref = command_data["artifact_ref"]
    artifact_ref["artifact_sha256"] = by_role["strategy_wheel"]["sha256"]
    artifact_ref["artifact_size_bytes"] = by_role["strategy_wheel"]["size_bytes"]
    artifact_ref["manifest_sha256"] = by_role["strategy_manifest"]["sha256"]
    artifact_ref["manifest_size_bytes"] = by_role["strategy_manifest"]["size_bytes"]
    artifact_ref["sbom_sha256"] = by_role["sbom"]["sha256"]
    artifact_ref["contract_schema_sha256"] = by_role["contract_schema"]["sha256"]
    artifact_ref["required_runtime_artifacts"] = [
        member for member in members if member["role"] == "runtime_artifact"
    ]
    attestation = artifact_ref["attestation"]
    attestation["bundle_sha256"] = by_role["attestation_bundle"]["sha256"]
    attestation["normalized_source_tree_sha256"] = by_role["source_tree"]["sha256"]
    attestation["trust_policy_id"] = trust_policy_id
    attestation["trust_policy_version"] = trust_policy_version
    attestation["trust_policy_digest"] = trust_policy_digest

    bom_bytes = canonical_json_bytes(
        {
            "schema_version": "alephain.strategy-release-bom.v1",
            "members": members,
        }
    )
    command_data["release_bom_digest"] = sha256_hex(bom_bytes)
    command = StrategyExecutionCommandBindingV1.model_validate(command_data)
    return ArtifactFixture(command, bom_bytes, member_paths, manifest_bytes)
