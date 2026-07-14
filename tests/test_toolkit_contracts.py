from __future__ import annotations

import copy
import json
import subprocess
import sys
import tomllib
from decimal import Decimal
from pathlib import Path

import pytest
from custos_toolkit.contracts.strategy_execution import (
    DevelopmentSourceRefV1,
    StrategyArtifactRefV1,
    StrategyArtifactVerificationReceiptV1,
    StrategyExecutionCommandBindingV1,
    StrategyExecutionContextV1,
    StrategyManifestV1,
    canonical_json_bytes,
    canonical_json_digest,
    deep_freeze_json,
    parse_and_freeze_json_object,
    verify_effective_config_digest,
)
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_MODELS = {
    "strategy_execution_context_v1.schema.json": StrategyExecutionContextV1,
    "strategy_manifest_v1.schema.json": StrategyManifestV1,
    "strategy_artifact_ref_v1.schema.json": StrategyArtifactRefV1,
    "development_source_ref_v1.schema.json": DevelopmentSourceRefV1,
    "strategy_execution_command_binding_v1.schema.json": StrategyExecutionCommandBindingV1,
    "strategy_artifact_verification_receipt_v1.schema.json": StrategyArtifactVerificationReceiptV1,
}


def _golden() -> dict[str, object]:
    path = ROOT / "docs/authority/strategy-artifact-lifecycle-golden-v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_context_rejects_legacy_deployment_id() -> None:
    value = {
        "engine": "nautilus",
        "trading_mode": "sandbox",
        "deployment_instance_id": "20000000-0000-4000-8000-000000000002",
        "deployment_spec_id": "30000000-0000-4000-8000-000000000003",
        "deployment_spec_digest": "d" * 64,
        "effective_config_digest": "e" * 64,
        "generation": 1,
        "deployment_id": "legacy",
    }
    with pytest.raises(ValidationError):
        StrategyExecutionContextV1.model_validate(value)


def test_effective_config_is_decimal_and_deep_frozen() -> None:
    frozen = parse_and_freeze_json_object('{"nested":{"values":[1,1.25]}}')
    nested = frozen["nested"]
    assert nested["values"] == (1, Decimal("1.25"))
    with pytest.raises(TypeError):
        frozen["new"] = "value"
    with pytest.raises(TypeError, match="float"):
        deep_freeze_json({"threshold": 1.25})


def test_effective_config_rejects_duplicate_and_non_finite_numbers() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        parse_and_freeze_json_object('{"period":10,"period":11}')
    with pytest.raises(ValueError, match="non-finite"):
        parse_and_freeze_json_object('{"threshold":NaN}')


def test_effective_config_digest_is_checked() -> None:
    raw = '{"period":10,"threshold":1.25}'
    expected = canonical_json_digest({"period": 10, "threshold": Decimal("1.25")})
    assert verify_effective_config_digest(raw, expected)["period"] == 10
    with pytest.raises(ValueError, match="digest"):
        verify_effective_config_digest(raw, "0" * 64)


def test_canonical_json_normalizes_key_order_unicode_decimal_and_negative_zero() -> None:
    value = {
        "\u00e9": "\u2603",
        "z": Decimal("1.2300"),
        "a": Decimal("-0"),
        "n": Decimal("1E+3"),
    }

    assert canonical_json_bytes(value) == '{"a":0,"n":1000,"z":1.23,"\u00e9":"\u2603"}'.encode()
    assert canonical_json_digest(value) == canonical_json_digest(
        {"a": 0, "n": 1000, "z": Decimal("1.23"), "\u00e9": "\u2603"}
    )


def test_canonical_json_rejects_non_string_keys_and_non_finite_decimals() -> None:
    with pytest.raises(TypeError, match="keys must be strings"):
        canonical_json_bytes({1: "not-a-contract-key"})
    with pytest.raises(ValueError, match="finite"):
        canonical_json_bytes({"threshold": Decimal("Infinity")})


def test_artifact_ref_rejects_business_authority_fields() -> None:
    value = dict(_golden()["artifact_ref"])
    value["strategy_release_id"] = "50000000-0000-4000-8000-000000000005"
    with pytest.raises(ValidationError):
        StrategyArtifactRefV1.model_validate(value)


@pytest.mark.parametrize(
    "role",
    [
        "strategy_wheel",
        "strategy_manifest",
        "runtime_artifact",
        "attestation_bundle",
        "sbom",
        "contract_schema",
        "source_tree",
    ],
)
def test_release_bom_member_digest_substitution_is_rejected(role: str) -> None:
    command = copy.deepcopy(_golden()["signed_command"]["strategy_artifact_binding"])
    member = next(item for item in command["release_bom_members"] if item["role"] == role)
    member["sha256"] = "0" * 64

    with pytest.raises(ValidationError):
        StrategyExecutionCommandBindingV1.model_validate(command)


def test_contract_models_reject_unknown_fields_recursively() -> None:
    command = copy.deepcopy(_golden()["signed_command"]["strategy_artifact_binding"])
    command["unknown_command_field"] = "forbidden"
    with pytest.raises(ValidationError):
        StrategyExecutionCommandBindingV1.model_validate(command)

    command = copy.deepcopy(_golden()["signed_command"]["strategy_artifact_binding"])
    command["release_bom_members"][0]["unknown_member_field"] = "forbidden"
    with pytest.raises(ValidationError):
        StrategyExecutionCommandBindingV1.model_validate(command)

    receipt = copy.deepcopy(_golden()["custos_verifier_receipt"])
    receipt["unknown_receipt_field"] = "forbidden"
    with pytest.raises(ValidationError):
        StrategyArtifactVerificationReceiptV1.model_validate(receipt)


def test_verification_receipt_rejects_artifact_digest_substitution() -> None:
    receipt = copy.deepcopy(_golden()["custos_verifier_receipt"])
    receipt["artifact_ref_digest"] = "0" * 64

    with pytest.raises(ValidationError):
        StrategyArtifactVerificationReceiptV1.model_validate(receipt)


def test_verification_receipt_rejects_trust_policy_mismatch() -> None:
    receipt = copy.deepcopy(_golden()["custos_verifier_receipt"])
    receipt["local_trust_policy_digest"] = "0" * 64

    with pytest.raises(ValidationError):
        StrategyArtifactVerificationReceiptV1.model_validate(receipt)


def test_verification_receipt_rejects_unknown_profile() -> None:
    receipt = copy.deepcopy(_golden()["custos_verifier_receipt"])
    receipt["verification_profile"] = "untrusted-profile"

    with pytest.raises(ValidationError):
        StrategyArtifactVerificationReceiptV1.model_validate(receipt)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("deployment_instance_id", "not-an-instance-uuid"),
        ("deployment_spec_id", "not-a-spec-uuid"),
        ("deployment_spec_digest", "d" * 63),
        ("effective_config_digest", "e" * 63),
        ("release_bom_digest", "f" * 63),
        ("generation", 0),
    ],
)
def test_command_rejects_invalid_identity_digest_and_generation(
    field: str, invalid: object
) -> None:
    command = copy.deepcopy(_golden()["signed_command"]["strategy_artifact_binding"])
    command[field] = invalid

    with pytest.raises(ValidationError):
        StrategyExecutionCommandBindingV1.model_validate(command)


def test_golden_cross_links_instance_spec_digests_and_bom() -> None:
    golden = _golden()
    command = golden["signed_command"]["strategy_artifact_binding"]
    receipt = golden["custos_verifier_receipt"]
    deployment_spec = golden["deployment_spec"]
    strategy_release = golden["strategy_release"]
    artifact_ref = golden["artifact_ref"]

    assert receipt["command_binding"] == command
    assert receipt["verified_members"] == command["release_bom_members"]
    assert receipt["command_binding"]["deployment_instance_id"] == command["deployment_instance_id"]
    assert receipt["command_binding"]["generation"] == command["generation"]
    assert command["deployment_spec_id"] == deployment_spec["deployment_spec_id"]
    assert command["deployment_spec_digest"] == deployment_spec["deployment_spec_digest"]
    assert command["effective_config_digest"] == deployment_spec["effective_config_digest"]
    assert command["strategy_release_id"] == strategy_release["strategy_release_id"]
    assert command["release_bom_digest"] == strategy_release["release_bom_digest"]
    assert command["release_bom_members"] == strategy_release["release_bom_members"]
    assert command["artifact_ref"] == artifact_ref

    members_by_role = {member["role"]: member for member in command["release_bom_members"]}
    assert members_by_role["strategy_wheel"]["sha256"] == artifact_ref["artifact_sha256"]
    assert members_by_role["strategy_manifest"]["sha256"] == artifact_ref["manifest_sha256"]
    assert (
        members_by_role["attestation_bundle"]["sha256"]
        == artifact_ref["attestation"]["bundle_sha256"]
    )
    assert members_by_role["sbom"]["sha256"] == artifact_ref["sbom_sha256"]
    assert members_by_role["contract_schema"]["sha256"] == artifact_ref["contract_schema_sha256"]
    assert (
        members_by_role["source_tree"]["sha256"]
        == artifact_ref["attestation"]["normalized_source_tree_sha256"]
    )
    assert artifact_ref["required_runtime_artifacts"][0] in command["release_bom_members"]


def test_lifecycle_golden_is_lossless() -> None:
    golden = _golden()
    command = golden["signed_command"]["strategy_artifact_binding"]
    receipt = golden["custos_verifier_receipt"]
    StrategyExecutionCommandBindingV1.model_validate(command)
    StrategyArtifactVerificationReceiptV1.model_validate(receipt)
    assert receipt["command_binding"] == command
    assert receipt["verified_members"] == command["release_bom_members"]
    assert golden["strategy_release"]["deployment_spec_id"] is None


@pytest.mark.parametrize(("filename", "model"), SCHEMA_MODELS.items())
def test_schema_is_source_generated(filename: str, model: type) -> None:
    path = ROOT / "docs/gateway-contract/v1" / filename
    assert json.loads(path.read_text(encoding="utf-8")) == model.model_json_schema(
        mode="validation"
    )


def test_lightweight_import_does_not_load_nautilus_or_mutate_path() -> None:
    script = (
        "import sys; before=tuple(sys.path); "
        "import custos.contracts.strategy_execution; "
        "assert tuple(sys.path)==before; assert 'nautilus_trader' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", script], check=True)


def test_root_python311_consumes_separate_toolkit_distributions() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    nautilus_requirements = project["optional-dependencies"]["nautilus"]

    assert project["requires-python"] == ">=3.11"
    assert "custos-strategy-toolkit==0.1.0" in project["dependencies"]
    assert "custos-strategy-toolkit-nautilus==0.1.0" in nautilus_requirements
    assert all("nautilus-trader" not in requirement for requirement in nautilus_requirements)
    assert all("python_version" not in requirement for requirement in nautilus_requirements)
