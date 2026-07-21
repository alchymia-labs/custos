from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/gateway-contract/v1"


def test_custos_does_not_publish_crucible_deployment_spec_assets() -> None:
    assert not (CONTRACT / "deployment_spec.schema.json").exists()
    assert not (CONTRACT / "samples/deployment_spec_sandbox.json").exists()


def test_gateway_readme_teaches_the_single_owner_boundary() -> None:
    text = " ".join((CONTRACT / "README.md").read_text(encoding="utf-8").split())

    assert "does not publish a DeploymentSpec schema" in text
    assert "Crucible owns the canonical DeploymentSpec" in text
    assert "authenticated Crucible `StrategyRelease` authority" in text
    assert "arx-runner deployment" not in text
