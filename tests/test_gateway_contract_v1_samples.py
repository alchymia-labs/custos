from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

CONTRACT_DIR = Path(__file__).resolve().parent.parent / "docs" / "gateway-contract" / "v1"
SAMPLE_CASES = (
    ("enrollment", "enrollment"),
    ("deployment_status", "deployment_status"),
    ("telemetry_snapshot", "telemetry_snapshot"),
    ("heartbeat", "heartbeat"),
    ("deployment_spec_sandbox", "deployment_spec"),
)


def _load_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


@pytest.mark.parametrize(("sample_name", "schema_name"), SAMPLE_CASES)
def test_gateway_contract_sample_validates_against_schema(
    sample_name: str,
    schema_name: str,
) -> None:
    schema = _load_json(CONTRACT_DIR / f"{schema_name}.schema.json")
    sample = _load_json(CONTRACT_DIR / "samples" / f"{sample_name}.json")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(sample)


def test_informative_deployment_spec_allows_arx_owned_extensions() -> None:
    schema = _load_json(CONTRACT_DIR / "deployment_spec.schema.json")
    sample = _load_json(CONTRACT_DIR / "samples" / "deployment_spec_sandbox.json")
    sample["approved_by"] = ["alice", "bob"]
    sample["risk_config"] = {"max_notional_per_runner": "200"}
    Draft202012Validator(schema).validate(sample)
