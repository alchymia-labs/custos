import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_authority_manifest_is_standalone_resolvable() -> None:
    manifest = json.loads((ROOT / "authority-manifest.json").read_text())
    for entry in manifest["authority_documents"]:
        assert not entry["path"].startswith("..")
        assert (ROOT / entry["path"]).is_file()


def test_authority_snapshot_pins_single_topology_and_heads() -> None:
    snapshot = json.loads((ROOT / "docs/authority/ecosystem-authority.json").read_text())
    assert snapshot["runtime_identity"] == "deployment_instance_id"
    assert snapshot["fact_kind"] == "RunnerDeploymentLifecycleFact.v1"
    assert snapshot["deployment_spec_digest"]["algorithm"] == "sha256-canonical-json-v1"
    assert snapshot["migration_heads"] == {
        "arx": "0068", "crucible_control": "0026", "crucible_mode": "0113"
    }
