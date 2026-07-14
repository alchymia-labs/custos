import json
from pathlib import Path

from custos.contracts import DeploymentSpec

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/gateway-contract/v1"


def test_deployment_schema_is_generated_from_current_model() -> None:
    checked_in = json.loads((CONTRACT / "deployment_spec.schema.json").read_text())
    assert checked_in == DeploymentSpec.model_json_schema()


def test_sandbox_sample_matches_current_local_execution_view() -> None:
    sample = json.loads((CONTRACT / "samples/deployment_spec_sandbox.json").read_text())
    assert DeploymentSpec.model_validate(sample).deployment_instance_id
