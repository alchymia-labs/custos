from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
import yaml

from custos.contracts import DeploymentSpec

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
SANDBOX_DIR = EXAMPLES_DIR / "supertrend-sandbox"
TESTNET_DIR = EXAMPLES_DIR / "supertrend-testnet"
LEGACY_TOKENS = (
    "--sops-file",
    "--age-key-file",
    "python -m custos",
    "--use-nt-host",
)
TEXT_FILES = (
    SANDBOX_DIR / "README.md",
    TESTNET_DIR / "README.md",
    TESTNET_DIR / ".env.example",
    TESTNET_DIR / "docker-compose.yaml",
)
ACTIVE_RUNTIME_DOCS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "ops" / "05-deployment.md",
    SANDBOX_DIR / "README.md",
    TESTNET_DIR / "README.md",
)
LOCAL_IMAGE = "custos-runner:v0.3.0"
REMOTE_IMAGE = "ghcr.io/the-alephain-guild/custos:v0.3.0"
PLAN_14 = REPO_ROOT / ".forge" / "plans" / "2026-07" / "14-clean-deployment-runtime-contract.md"
VERIFICATION_RULE = REPO_ROOT / ".claude" / "rules" / "verification.md"


def test_project_and_lock_are_versioned_v030() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked_project = next(
        package for package in lock["package"] if package["name"] == "custos-runner"
    )

    assert project["project"]["version"] == "0.3.0"
    assert locked_project["version"] == "0.3.0"


def test_changelog_documents_v030_clean_break() -> None:
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    v030 = text[text.index("## [0.3.0]") : text.index("## [0.2.0]")]

    assert "## [0.3.0] - 2026-07-12" in text
    assert LOCAL_IMAGE in v030
    assert "Remote release: deferred" in v030
    assert REMOTE_IMAGE not in v030
    for contract in (
        "--engine",
        "--use-nt-host",
        "generation",
        "lifecycle_state",
        "deployment publish",
        "nats bootstrap",
        "health",
    ):
        assert contract in text


def test_readme_declares_local_image_and_downstream_gate() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert LOCAL_IMAGE in text
    assert "make verify-local-v030" in text
    assert "Remote release: deferred" in text
    assert REMOTE_IMAGE not in text
    assert "PS Plan 49 must not execute against custos < 0.3.0." in text
    assert "PS must consume the verified local image directly." in text
    assert "PS must not maintain a derived custos Dockerfile." in text
    assert "PS owns strategy_config assembly only." in text


def test_remote_release_follow_up_names_identity_decisions() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    for decision in (
        "GitHub repository",
        "GHCR namespace",
        "cosign identity",
        "tag ownership",
        "PyPI trusted publisher identity",
    ):
        assert decision in text


@pytest.mark.parametrize("path", TEXT_FILES, ids=lambda path: str(path.relative_to(REPO_ROOT)))
def test_example_text_has_no_legacy_cli_tokens(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for token in LEGACY_TOKENS:
        assert token not in text


@pytest.mark.parametrize(
    "path", ACTIVE_RUNTIME_DOCS, ids=lambda path: str(path.relative_to(REPO_ROOT))
)
def test_active_runtime_docs_do_not_use_removed_engine_flag(path: Path) -> None:
    assert "--use-nt-host" not in path.read_text(encoding="utf-8")


def test_testnet_compose_uses_v030_official_runtime_shape() -> None:
    compose = yaml.safe_load((TESTNET_DIR / "docker-compose.yaml").read_text(encoding="utf-8"))
    runner = compose["services"]["runner"]
    bootstrap = compose["services"]["nats-bootstrap"]
    publisher = compose["services"]["spec-publisher"]

    assert "build" not in runner
    for service in (runner, bootstrap, publisher):
        assert service["image"] == LOCAL_IMAGE
        assert service["pull_policy"] == "never"
    assert runner["command"][0] == "start"
    assert ["--engine", "nautilus"] == runner["command"][5:7]
    assert runner["depends_on"]["nats-bootstrap"]["condition"] == "service_completed_successfully"
    assert runner["healthcheck"]["test"] == ["CMD", "arx-runner", "health"]
    assert "./runtime/.arx:/home/custos/.arx" in runner["volumes"]

    assert bootstrap["command"][0:2] == ["nats", "bootstrap"]
    assert publisher["command"][0:2] == ["deployment", "publish"]
    assert publisher["depends_on"]["runner"]["condition"] == "service_healthy"


def test_testnet_readme_requires_local_image_gate() -> None:
    text = (TESTNET_DIR / "README.md").read_text(encoding="utf-8")

    assert "make verify-local-v030" in text
    assert LOCAL_IMAGE in text
    assert REMOTE_IMAGE not in text


def test_local_consumer_gate_is_registered_and_amends_plan_14() -> None:
    verification = VERIFICATION_RULE.read_text(encoding="utf-8")
    plan_14 = PLAN_14.read_text(encoding="utf-8")

    assert "make verify-local-v030" in verification
    assert "Plan 16 verified local image" in plan_14
    assert "PS local-development gate" in plan_14


def test_testnet_example_has_no_derived_dockerfile() -> None:
    assert not (TESTNET_DIR / "Dockerfile").exists()


def test_testnet_env_contains_only_non_secret_runtime_keys() -> None:
    values = {}
    for raw_line in (TESTNET_DIR / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    assert set(values) == {
        "ARX_TENANT_ID",
        "ARX_RUNNER_ID",
        "ARX_NATS_URL",
        "ARX_STRATEGY_ID",
    }
    assert all("KEY" not in key and "SECRET" not in key for key in values)


def test_testnet_vault_fixture_is_one_per_key_payload() -> None:
    fixture = json.loads(
        (TESTNET_DIR / "vault-fixture" / "credentials.example.json").read_text(encoding="utf-8")
    )
    assert list(fixture) == ["binance-testnet"]
    assert set(fixture["binance-testnet"]) == {
        "api_key",
        "api_secret",
        "permission_scope",
    }
    assert fixture["binance-testnet"]["permission_scope"] == "trade_no_withdraw"


def test_examples_sandbox_spec_matches_gateway_sample() -> None:
    assert (SANDBOX_DIR / "spec-example.json").read_bytes() == (
        REPO_ROOT / "docs" / "gateway-contract" / "v1" / "samples" / "deployment_spec_sandbox.json"
    ).read_bytes()


@pytest.mark.parametrize(
    "path",
    (SANDBOX_DIR / "spec-example.json", TESTNET_DIR / "spec-example.json"),
)
def test_example_specs_are_complete_runtime_contracts(path: Path) -> None:
    spec = DeploymentSpec.model_validate_json(path.read_text(encoding="utf-8"))

    assert spec.strategy_config
    assert spec.strategy_registry_name == "supertrend"


def test_gateway_docs_teach_public_deployment_seam() -> None:
    text = (REPO_ROOT / "docs" / "gateway-contract" / "v1" / "README.md").read_text(
        encoding="utf-8"
    )

    assert "DeploymentMessage" in text
    assert "deployment publish" in text


@pytest.mark.parametrize("path", (SANDBOX_DIR / "README.md", TESTNET_DIR / "README.md"))
def test_example_readme_teaches_v030_three_step_flow(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "arx-runner vault put" in text
    assert "runner.toml" in text
    assert "arx-runner start" in text or "docker compose up" in text
    assert "trade_no_withdraw" in text
