"""Wire shape pinning — Python side (WR-NATS-3).

Loads the same fixtures the Rust integration test consumes and asserts
the producer-side schema invariants: payload_schema_version key
present, envelope keys complete, recon_result subject demux fields
unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = (
    REPO_ROOT
    / "backend"
    / "crates"
    / "telemetry"
    / "tests"
    / "wire_shapes"
)

FIXTURE_NAMES = ("heartbeat", "telemetry_snapshot", "recon_result")


def _load(name: str) -> dict:
    path = FIXTURE_DIR / f"{name}.json"
    return json.loads(path.read_bytes())


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_envelope_keys_complete(name: str) -> None:
    env = _load(name)
    for key in (
        "envelope_version",
        "event_id",
        "tenant_id",
        "occurred_at",
        "payload_schema_version",
        "payload",
    ):
        assert key in env, f"{name} missing {key}"


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_envelope_uses_payload_schema_version_not_legacy(name: str) -> None:
    env = _load(name)
    assert (
        "schema_version" not in env
    ), f"{name} regressed to legacy schema_version key"


def test_heartbeat_payload_complete() -> None:
    env = _load("heartbeat")
    assert set(env["payload"].keys()) == {
        "runner_id",
        "uptime_secs",
        "active_deployments",
        "health",
    }


def test_telemetry_snapshot_carries_equity_currency() -> None:
    env = _load("telemetry_snapshot")
    assert env["payload"]["equity_currency"] == "Usd"
    # Decimal serialised as string so backend rust_decimal parses losslessly.
    assert env["payload"]["equity"] == "12345.67891234"


def test_recon_result_payload_carries_dimension() -> None:
    env = _load("recon_result")
    assert env["payload"]["dimension"] == "balance"
    assert env["payload"]["scope"] == "account-1"
