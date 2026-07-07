"""TelemetryActor unit tests — Plan 04 Task 8.

The actor never imports nautilus_trader at module load, so we test it
with a fake publisher that records every published envelope. Coverage
locks the schema-whitelist filter, the monotonic seq invariant, session
stability across the actor's lifetime, and the batching contract.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import pytest

from arx_runner.nats_client import NatsEnvelope
from arx_runner.telemetry_actor import TelemetryActor, TelemetryActorConfig


@dataclass
class FakePublisher:
    """Records every call so tests can assert order and content."""

    telemetry_calls: list[tuple[str, NatsEnvelope]] = field(default_factory=list)
    heartbeat_calls: list[tuple[str, NatsEnvelope]] = field(default_factory=list)

    async def publish_telemetry(self, *, session_id: str, envelope: NatsEnvelope) -> None:
        self.telemetry_calls.append((session_id, envelope))

    async def publish_heartbeat_fire_and_forget(
        self, *, session_id: str, envelope: NatsEnvelope
    ) -> None:
        self.heartbeat_calls.append((session_id, envelope))


def make_actor(
    *,
    allowed: set[str] | None = None,
    batch_size: int = 50,
    flush_interval: float = 0.05,
    heartbeat_interval: float = 0.05,
) -> tuple[TelemetryActor, FakePublisher]:
    pub = FakePublisher()
    actor = TelemetryActor(
        publisher=pub,
        tenant_id="acme",
        runner_id="runner-001",
        config=TelemetryActorConfig(
            allowed_event_types=frozenset(allowed or {"OrderFillReport"}),
            batch_size=batch_size,
            flush_interval_secs=flush_interval,
            heartbeat_interval_secs=heartbeat_interval,
        ),
    )
    return actor, pub


@pytest.mark.asyncio
async def test_whitelist_filters_unknown_event_types():
    actor, pub = make_actor(allowed={"OrderFillReport"})
    actor.on_event("OrderFillReport", {"order_id": "o1"})
    actor.on_event("AccountState", {"balance": 100})  # not in whitelist
    actor.on_event("OrderFillReport", {"order_id": "o2"})
    await actor.start()
    await asyncio.sleep(0.1)
    await actor.stop()

    assert len(pub.telemetry_calls) == 2
    types = [env.payload["event_type"] for _, env in pub.telemetry_calls]
    assert types == ["OrderFillReport", "OrderFillReport"]


@pytest.mark.asyncio
async def test_seq_is_monotonic_within_a_session():
    actor, pub = make_actor()
    for i in range(3):
        actor.on_event("OrderFillReport", {"order_id": f"o{i}"})
    await actor.start()
    await asyncio.sleep(0.1)
    await actor.stop()

    seqs = [env.ordering.seq for _, env in pub.telemetry_calls]
    assert seqs == [1, 2, 3]


@pytest.mark.asyncio
async def test_session_id_is_stable_across_events():
    actor, pub = make_actor()
    for i in range(3):
        actor.on_event("OrderFillReport", {"order_id": f"o{i}"})
    await actor.start()
    await asyncio.sleep(0.1)
    await actor.stop()

    session_ids = {env.ordering.session_id for _, env in pub.telemetry_calls}
    assert len(session_ids) == 1
    assert session_ids.pop() == actor.session_id


@pytest.mark.asyncio
async def test_envelope_carries_plan_index_section_6_keys():
    actor, pub = make_actor()
    actor.on_event("OrderFillReport", {"order_id": "o1"})
    await actor.start()
    await asyncio.sleep(0.1)
    await actor.stop()

    assert len(pub.telemetry_calls) == 1
    _, env = pub.telemetry_calls[0]
    raw = json.loads(env.to_bytes())
    for key in (
        "envelope_version",
        "event_id",
        "tenant_id",
        "occurred_at",
        "payload_schema_version",
        "payload",
        "ordering",
    ):
        assert key in raw, f"plan-index §6 mandates {key}"
    assert raw["tenant_id"] == "acme"
    assert raw["ordering"]["session_id"] == actor.session_id


@pytest.mark.asyncio
async def test_heartbeat_loop_emits_at_least_one_beat():
    actor, pub = make_actor(heartbeat_interval=0.02)
    await actor.start()
    await asyncio.sleep(0.1)
    await actor.stop()

    assert len(pub.heartbeat_calls) >= 1
    _, env = pub.heartbeat_calls[0]
    # Plan-index §6 + Rust HeartbeatPayload struct require all four fields.
    assert env.payload["runner_id"] == "runner-001"
    assert "uptime_secs" in env.payload
    assert "active_deployments" in env.payload
    assert env.payload["health"] == "online"


@pytest.mark.asyncio
async def test_event_ids_are_uuid_v7():
    actor, pub = make_actor()
    actor.on_event("OrderFillReport", {"order_id": "o1"})
    await actor.start()
    await asyncio.sleep(0.05)
    await actor.stop()

    assert len(pub.telemetry_calls) == 1
    _, env = pub.telemetry_calls[0]
    # UUIDv7 sets the version nibble at the 13th hex char (offset 14 in
    # the canonical hyphenated form: 8-4-[v]xxx-4-12).
    assert env.event_id[14] == "7", env.event_id
    assert env.ordering is not None
    # session_id is also UUIDv7 so consumer-side watermark can compare
    # session boundaries by the embedded unix_ts_ms prefix.
    assert env.ordering.session_id[14] == "7", env.ordering.session_id


@pytest.mark.asyncio
async def test_batch_flushes_pending_events_on_stop():
    # Large batch_size + short queue → stop() must still drain.
    actor, pub = make_actor(batch_size=100, flush_interval=0.5)
    actor.on_event("OrderFillReport", {"order_id": "o1"})
    actor.on_event("OrderFillReport", {"order_id": "o2"})
    await actor.start()
    await asyncio.sleep(0.05)
    await actor.stop()

    assert len(pub.telemetry_calls) == 2
