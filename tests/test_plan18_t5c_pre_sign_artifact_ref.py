from __future__ import annotations

import json
from pathlib import Path

import pytest
from custos_toolkit.contracts.strategy_execution import (
    StrategyArtifactRefV2,
    canonical_model_digest,
)
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs/gateway-contract/v3/strategy_artifact_ref_v2.schema.json"
GOLDEN = ROOT / "docs/authority/strategy-artifact-ref-pre-sign-golden-v3.json"
INDEX = ROOT / "docs/authority/strategy-contract-assets-v3.json"
LEGACY_V1_GOLDEN = ROOT / "docs/authority/strategy-artifact-lifecycle-golden-v1.json"
LEGACY_V2_GOLDEN = ROOT / "docs/authority/strategy-artifact-pre-import-lifecycle-golden-v2.json"

ALLOWED_FIELDS = {
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
FORBIDDEN_FIELDS = {
    "attestation",
    "attestation_bundle",
    "bundle_coordinate",
    "bundle_sha256",
    "certificate",
    "certificate_chain",
    "issuer",
    "workflow_identity",
    "sigstore",
    "signer",
    "transparency_log",
    "transparency_log_verified",
    "trust_policy_id",
    "trust_policy_version",
    "trust_policy_digest",
    "trusted_root_digest",
    "verified_subjects",
    "verification_profile",
}


def _golden() -> dict[str, object]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_artifact_ref_is_exactly_the_pre_sign_execution_identity() -> None:
    document = _golden()
    artifact_ref = document["artifact_ref"]
    parsed = StrategyArtifactRefV2.model_validate(artifact_ref)

    assert set(artifact_ref) == ALLOWED_FIELDS
    assert set(artifact_ref).isdisjoint(FORBIDDEN_FIELDS)
    assert parsed.artifact_kind == "wheel"
    assert parsed.schema_version == 2
    assert parsed.engine == "nautilus"
    assert parsed.engine_version == "1.230.0"
    assert parsed.build_inputs
    assert parsed.required_runtime_artifacts
    assert document["artifact_ref_digest"] == canonical_model_digest(parsed)
    assert document["production_handoff_ready"] is False


@pytest.mark.parametrize(
    "field",
    sorted(FORBIDDEN_FIELDS),
)
def test_artifact_ref_rejects_bundle_policy_and_post_verification_fields(field: str) -> None:
    value = dict(_golden()["artifact_ref"])
    value[field] = "forbidden"

    with pytest.raises(ValidationError):
        StrategyArtifactRefV2.model_validate(value)


def test_v3_schema_is_the_only_current_artifact_ref_schema() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    index = json.loads(INDEX.read_text(encoding="utf-8"))

    assert schema == StrategyArtifactRefV2.model_json_schema(mode="validation")
    assert set(schema["properties"]) == ALLOWED_FIELDS
    assert set(schema["properties"]).isdisjoint(FORBIDDEN_FIELDS)
    assert index["current_artifact_ref_schema"] == str(SCHEMA.relative_to(ROOT))
    assert index["candidate_status"] == "PRE_SIGN_ABI_ONLY"
    assert index["handoff_ready"] is False
    assert index["production_ready"] is False
    assert index["legacy_non_production"]["v1"]["runtime_fallback_allowed"] is False
    assert index["legacy_non_production"]["v2"]["runtime_fallback_allowed"] is False


def test_legacy_v1_and_v2_embedded_attestation_cannot_parse_as_current_artifact_ref() -> None:
    legacy_v1 = json.loads(LEGACY_V1_GOLDEN.read_text(encoding="utf-8"))["artifact_ref"]
    legacy_v2 = json.loads(LEGACY_V2_GOLDEN.read_text(encoding="utf-8"))["command_binding"][
        "artifact_ref"
    ]

    assert "attestation" in legacy_v1
    assert "attestation" in legacy_v2
    with pytest.raises(ValidationError):
        StrategyArtifactRefV2.model_validate(legacy_v1)
    with pytest.raises(ValidationError):
        StrategyArtifactRefV2.model_validate(legacy_v2)
