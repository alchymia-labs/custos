"""F4/IN-NATS-1: every NATS publish-site subject must flow through
``build_subject`` so empty tokens raise rather than silently producing a
malformed subject like ``arx.acme.telemetry.`` (which NATS rejects but
silently from the producer's perspective).

Three contracts pinned here:

1. ``heartbeat_subject`` delegates to ``build_subject`` (rejects empty
   tenant or runner ids).
2. ``ArxNatsTelemetryAdapter.publish_telemetry`` raises ``ValueError`` if
   any of tenant / runner_id / session_id is empty.
3. ``ArxNatsTelemetryAdapter.publish_heartbeat_fire_and_forget`` raises
   on empty tenant or runner_id.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from arx_runner.nats_client import (
    ArxNatsClient,
    NatsEnvelope,
    OrderingMeta,
    build_subject,
    heartbeat_subject,
)
from arx_runner.telemetry_actor import ArxNatsTelemetryAdapter


def _envelope() -> NatsEnvelope:
    return NatsEnvelope(
        envelope_version=1,
        event_id="01900000-0000-7000-8000-000000000abc",
        tenant_id="acme",
        occurred_at="2026-06-26T10:00:00.000000000Z",
        payload_schema_version=1,
        payload={"runner_id": "r-001", "health": "online"},
        ordering=OrderingMeta(session_id="01900000-0000-7000-8000-000000000001", seq=1),
    )


def test_heartbeat_subject_routes_through_build_subject():
    # Same as before: well-formed inputs yield the canonical subject.
    assert heartbeat_subject("acme", "r-001") == "arx.acme.heartbeat.r-001"


@pytest.mark.parametrize(
    "tenant,runner",
    [("", "r-001"), ("acme", ""), ("", "")],
)
def test_heartbeat_subject_rejects_empty_tokens(tenant: str, runner: str):
    # F4: empty tokens used to inline-format into "arx..heartbeat.r-001"
    # silently — now build_subject's guard surfaces them.
    with pytest.raises(ValueError):
        heartbeat_subject(tenant, runner)


def test_build_subject_rejects_empty_path_parts():
    with pytest.raises(ValueError):
        build_subject("acme", "telemetry", "r-001", "")


@dataclass
class _FakeNatsClient:
    """Minimal stand-in covering only the fields/methods the adapter
    touches in this test (no real NATS connection)."""

    tenant_id: str
    runner_id: str
    published_subjects: list[str] = field(default_factory=list)

    async def publish_telemetry_envelope(self, subject: str, envelope: NatsEnvelope) -> None:
        self.published_subjects.append(subject)

    async def publish_fire_and_forget(self, subject: str, payload: bytes) -> None:
        self.published_subjects.append(subject)


def test_adapter_publish_telemetry_uses_build_subject():
    client = _FakeNatsClient(tenant_id="acme", runner_id="r-001")
    adapter = ArxNatsTelemetryAdapter(client=client)  # type: ignore[arg-type]
    asyncio.run(adapter.publish_telemetry(session_id="sess-1", envelope=_envelope()))
    assert client.published_subjects == ["arx.acme.telemetry.r-001.sess-1"]


@pytest.mark.parametrize(
    "tenant,runner,session",
    [
        ("", "r-001", "sess-1"),
        ("acme", "", "sess-1"),
        ("acme", "r-001", ""),
    ],
)
def test_adapter_publish_telemetry_rejects_empty_tokens(tenant: str, runner: str, session: str):
    client = _FakeNatsClient(tenant_id=tenant, runner_id=runner)
    adapter = ArxNatsTelemetryAdapter(client=client)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        asyncio.run(adapter.publish_telemetry(session_id=session, envelope=_envelope()))
    assert client.published_subjects == [], "no publish on malformed subject"


def test_adapter_publish_heartbeat_uses_build_subject():
    client = _FakeNatsClient(tenant_id="acme", runner_id="r-001")
    adapter = ArxNatsTelemetryAdapter(client=client)  # type: ignore[arg-type]
    asyncio.run(
        adapter.publish_heartbeat_fire_and_forget(session_id="sess-1", envelope=_envelope())
    )
    assert client.published_subjects == ["arx.acme.heartbeat.r-001"]


@pytest.mark.parametrize(
    "tenant,runner",
    [("", "r-001"), ("acme", "")],
)
def test_adapter_publish_heartbeat_rejects_empty_tokens(tenant: str, runner: str):
    client = _FakeNatsClient(tenant_id=tenant, runner_id=runner)
    adapter = ArxNatsTelemetryAdapter(client=client)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        asyncio.run(
            adapter.publish_heartbeat_fire_and_forget(session_id="sess-1", envelope=_envelope())
        )
    assert client.published_subjects == [], "no publish on malformed subject"


_unused_keep_alive = ArxNatsClient  # noqa: F841 — keep import to flag class rename
