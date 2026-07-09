"""Cross-language wire contract tests — Python producer bytes must decode
on the Rust consumer side.

Plan-index §6 wire envelope keys are wire-stable; this file pins them
from the Python side. The Rust counterpart in
``backend/crates/telemetry/tests/wire_shapes/`` loads the same fixtures
and decodes them with ``serde_json::from_slice``.
"""

from __future__ import annotations

import json

from custos.core.nats_client import build_heartbeat_envelope


def test_heartbeat_payload_includes_uptime_and_active_deployments() -> None:
    env = build_heartbeat_envelope(
        tenant_id="acme",
        runner_id="r-001",
        session_id="22222222-2222-2222-2222-222222222222",
        seq=1,
        health="online",
        uptime_secs=3600,
        active_deployments=2,
    )
    body = json.loads(env.to_bytes())
    payload = body["payload"]
    assert payload["runner_id"] == "r-001"
    assert payload["uptime_secs"] == 3600
    assert payload["active_deployments"] == 2
    assert payload["health"] == "online"


def test_heartbeat_payload_keys_match_rust_consumer_struct() -> None:
    """Rust ``HeartbeatPayload`` requires runner_id / uptime_secs /
    active_deployments / health — pinning the key set so a producer-side
    field rename can't drift past the cross-language round-trip."""
    env = build_heartbeat_envelope(
        tenant_id="acme",
        runner_id="r-001",
        session_id="22222222-2222-2222-2222-222222222222",
        seq=1,
        health="online",
        uptime_secs=0,
        active_deployments=0,
    )
    payload = json.loads(env.to_bytes())["payload"]
    assert set(payload.keys()) == {
        "runner_id",
        "uptime_secs",
        "active_deployments",
        "health",
    }
