"""Executable alignment gate for the top-level runtime authority document."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "docs" / "domain.md"


@pytest.mark.parametrize(
    "legacy_contract",
    [
        "\u4e0d\u76f4\u63a5\u8ddf arx \u901a\u4fe1",
        "arx.<tenant>.deployment.spec",
        "arx.<tenant>.deployment.status",
        "arx.<tenant>.runner.heartbeat",
        "~/.custos/vault",
    ],
)
def test_domain_rejects_legacy_runtime_contracts(legacy_contract: str) -> None:
    assert legacy_contract not in DOMAIN.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "current_contract",
    [
        "arx.<tenant>.deployment_spec.<strategy_id>",
        "arx.<tenant>.deployment_status.<runner_id>.<spec_id>",
        "arx.<tenant>.heartbeat.<runner_id>",
        "arx.<tenant>.telemetry.<runner_id>.<session_id>",
        "~/.arx/vault/<key-id>.enc",
    ],
)
def test_domain_pins_current_runtime_contracts(current_contract: str) -> None:
    assert current_contract in DOMAIN.read_text(encoding="utf-8")


def test_domain_names_arx_as_the_direct_runtime_peer() -> None:
    text = DOMAIN.read_text(encoding="utf-8")

    assert "Custos ↔ arx coordination plane" in text
    assert "Crucible is not a direct Custos runtime peer" in text
