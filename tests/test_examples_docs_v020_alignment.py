from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
SANDBOX_DIR = EXAMPLES_DIR / "supertrend-sandbox"
TESTNET_DIR = EXAMPLES_DIR / "supertrend-testnet"
LEGACY_TOKENS = ("--sops-file", "--age-key-file", "python -m custos")
TEXT_FILES = (
    SANDBOX_DIR / "README.md",
    TESTNET_DIR / "README.md",
    TESTNET_DIR / ".env.example",
    TESTNET_DIR / "docker-compose.yaml",
)


@pytest.mark.parametrize("path", TEXT_FILES, ids=lambda path: str(path.relative_to(REPO_ROOT)))
def test_example_text_has_no_legacy_cli_tokens(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for token in LEGACY_TOKENS:
        assert token not in text


def test_testnet_compose_uses_v030_official_runtime_shape() -> None:
    compose = yaml.safe_load((TESTNET_DIR / "docker-compose.yaml").read_text(encoding="utf-8"))
    runner = compose["services"]["runner"]
    bootstrap = compose["services"]["nats-bootstrap"]
    publisher = compose["services"]["spec-publisher"]

    assert "build" not in runner
    assert runner["image"] == "ghcr.io/the-alephain-guild/custos:v0.3.0"
    assert runner["command"][0] == "start"
    assert ["--engine", "nautilus"] == runner["command"][5:7]
    assert runner["depends_on"]["nats-bootstrap"]["condition"] == "service_completed_successfully"
    assert runner["healthcheck"]["test"] == ["CMD", "arx-runner", "health"]
    assert "./runtime/.arx:/home/custos/.arx" in runner["volumes"]

    assert bootstrap["command"][0:2] == ["nats", "bootstrap"]
    assert publisher["command"][0:2] == ["deployment", "publish"]
    assert publisher["depends_on"]["runner"]["condition"] == "service_healthy"


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


@pytest.mark.parametrize("path", (SANDBOX_DIR / "README.md", TESTNET_DIR / "README.md"))
def test_example_readme_teaches_v020_three_step_flow(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "arx-runner vault put" in text
    assert "runner.toml" in text
    assert "arx-runner start" in text or "docker compose up" in text
    assert "trade_no_withdraw" in text
