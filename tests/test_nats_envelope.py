"""NatsEnvelope serialization contract.

Envelope shape pinned by plan-index §6 — every NATS message carries the
transport envelope; heartbeat / telemetry additionally carry `ordering`.
"""

from __future__ import annotations

import json
import re

import pytest

from custos.core.nats_client import NatsEnvelope, OrderingMeta, build_heartbeat_envelope

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
RFC3339_NS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{9}Z$")


def test_envelope_default_versions_are_v1() -> None:
    env = NatsEnvelope(
        event_id="00000000-0000-0000-0000-000000000000",
        tenant_id="acme",
        occurred_at="2026-06-25T10:00:00.000000000Z",
        payload={"health": "ok"},
    )
    assert env.envelope_version == 1
    assert env.payload_schema_version == 1


def test_envelope_round_trips_via_json() -> None:
    env = NatsEnvelope(
        event_id="11111111-2222-3333-4444-555555555555",
        tenant_id="acme",
        occurred_at="2026-06-25T10:00:00.123456789Z",
        payload={"health": "degraded"},
    )
    blob = env.to_bytes()
    decoded = json.loads(blob)
    assert decoded["envelope_version"] == 1
    assert decoded["event_id"] == "11111111-2222-3333-4444-555555555555"
    assert decoded["tenant_id"] == "acme"
    assert decoded["occurred_at"] == "2026-06-25T10:00:00.123456789Z"
    assert decoded["payload"] == {"health": "degraded"}
    assert "ordering" not in decoded  # heartbeat opt-in only


def test_heartbeat_envelope_includes_ordering() -> None:
    env = build_heartbeat_envelope(
        tenant_id="acme",
        runner_id="runner-7",
        session_id="22222222-2222-2222-2222-222222222222",
        seq=42,
        health="ok",
        uptime_secs=123,
        active_deployments=1,
    )
    decoded = json.loads(env.to_bytes())
    assert decoded["payload"]["health"] == "ok"
    assert decoded["payload"]["runner_id"] == "runner-7"
    assert decoded["payload"]["uptime_secs"] == 123
    assert decoded["payload"]["active_deployments"] == 1
    assert decoded["ordering"]["session_id"] == "22222222-2222-2222-2222-222222222222"
    assert decoded["ordering"]["seq"] == 42


def test_heartbeat_envelope_event_id_is_uuid() -> None:
    env = build_heartbeat_envelope(
        tenant_id="acme",
        runner_id="runner-7",
        session_id="22222222-2222-2222-2222-222222222222",
        seq=1,
        health="ok",
        uptime_secs=0,
        active_deployments=0,
    )
    assert UUID_RE.match(env.event_id), env.event_id
    # UUIDv7 sets the version nibble to '7'.
    assert env.event_id[14] == "7", env.event_id


def test_heartbeat_envelope_occurred_at_is_rfc3339_ns() -> None:
    env = build_heartbeat_envelope(
        tenant_id="acme",
        runner_id="runner-7",
        session_id="22222222-2222-2222-2222-222222222222",
        seq=1,
        health="ok",
        uptime_secs=0,
        active_deployments=0,
    )
    assert RFC3339_NS_RE.match(env.occurred_at), env.occurred_at


def test_ordering_meta_seq_must_be_non_negative() -> None:
    with pytest.raises(ValueError):
        OrderingMeta(session_id="22222222-2222-2222-2222-222222222222", seq=-1)
