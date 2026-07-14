from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from custos.contracts.strategy_execution import (
    DevelopmentSourceRefV1,
    StrategyArtifactRefV1,
    StrategyArtifactVerificationReceiptV1,
    StrategyExecutionCommandBindingV1,
    StrategyExecutionContextV1,
    StrategyManifestV1,
    canonical_json_digest,
    deep_freeze_json,
    parse_and_freeze_json_object,
    verify_effective_config_digest,
)

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


def test_artifact_ref_rejects_business_authority_fields() -> None:
    value = dict(_golden()["artifact_ref"])
    value["strategy_release_id"] = "50000000-0000-4000-8000-000000000005"
    with pytest.raises(ValidationError):
        StrategyArtifactRefV1.model_validate(value)


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
    assert json.loads(path.read_text(encoding="utf-8")) == model.model_json_schema(mode="validation")


def test_lightweight_import_does_not_load_nautilus_or_mutate_path() -> None:
    script = (
        "import sys; before=tuple(sys.path); "
        "import custos.contracts.strategy_execution; "
        "assert tuple(sys.path)==before; assert 'nautilus_trader' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", script], check=True)
