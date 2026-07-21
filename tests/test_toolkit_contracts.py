from __future__ import annotations

import hashlib
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
SOURCE_GENERATED_SCHEMA_MODELS = {
    "strategy_execution_context_v1.schema.json": StrategyExecutionContextV1,
    "strategy_manifest_v1.schema.json": StrategyManifestV1,
    "development_source_ref_v1.schema.json": DevelopmentSourceRefV1,
}


def _artifact_ref_golden() -> dict[str, object]:
    path = ROOT / "docs/authority/strategy-artifact-ref-v1.golden.json"
    return json.loads(path.read_text(encoding="utf-8"))["artifact_ref"]


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
        "é": "☃",
        "z": Decimal("1.2300"),
        "a": Decimal("-0"),
        "n": Decimal("1E+3"),
    }

    assert canonical_json_bytes(value) == '{"a":0,"n":1000,"z":1.23,"é":"☃"}'.encode()
    assert canonical_json_digest(value) == canonical_json_digest(
        {"a": 0, "n": 1000, "z": Decimal("1.23"), "é": "☃"}
    )


def test_canonical_json_rejects_non_string_keys_and_non_finite_decimals() -> None:
    with pytest.raises(TypeError, match="keys must be strings"):
        canonical_json_bytes({1: "not-a-contract-key"})
    with pytest.raises(ValueError, match="finite"):
        canonical_json_bytes({"threshold": Decimal("Infinity")})


def test_artifact_ref_rejects_business_authority_fields() -> None:
    value = dict(_artifact_ref_golden())
    value["strategy_release_id"] = "50000000-0000-4000-8000-000000000005"
    with pytest.raises(ValidationError):
        StrategyArtifactRefV1.model_validate(value)


@pytest.mark.parametrize(("filename", "model"), SOURCE_GENERATED_SCHEMA_MODELS.items())
def test_schema_is_source_generated(filename: str, model: type) -> None:
    path = ROOT / "docs/gateway-contract/v1" / filename
    assert json.loads(path.read_text(encoding="utf-8")) == model.model_json_schema(
        mode="validation"
    )


def test_artifact_ref_golden_matches_current_model_and_pin() -> None:
    golden_path = ROOT / "docs/authority/strategy-artifact-ref-v1.golden.json"
    sidecar = golden_path.with_suffix(golden_path.suffix + ".sha256")

    StrategyArtifactRefV1.model_validate(_artifact_ref_golden())
    assert (
        sidecar.read_text(encoding="ascii").split()[0]
        == hashlib.sha256(golden_path.read_bytes()).hexdigest()
    )


def test_lightweight_import_does_not_load_nautilus_or_mutate_path() -> None:
    script = (
        "import sys; before=tuple(sys.path); "
        "import custos_toolkit.contracts.strategy_execution; "
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
