"""ArxNatsClient telemetry extensions — Plan 04 Task 8.

These tests cover the subject builder + fire-and-forget + WAL drain
behaviour added on top of Plan 01's connect/publish_heartbeat scaffold.
The real NATS client is mocked so we never need a broker — Plan 04 is
about the runner-side state, the broker integration test lives with
Plan 01's deferred E1/E2 harness.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arx_runner.nats_client import (
    ArxNatsClient,
    NatsEnvelope,
    OrderingMeta,
    build_subject,
    heartbeat_subject,
)


def test_subject_builder_telemetry():
    assert (
        build_subject("acme", "telemetry", "runner-001", "session-abc")
        == "arx.acme.telemetry.runner-001.session-abc"
    )


def test_subject_builder_heartbeat_matches_canonical_form():
    canonical = heartbeat_subject("acme", "runner-001")
    via_builder = build_subject("acme", "heartbeat", "runner-001")
    assert canonical == via_builder == "arx.acme.heartbeat.runner-001"


def test_subject_builder_rejects_empty_parts():
    with pytest.raises(ValueError):
        build_subject("acme", "telemetry", "")
    with pytest.raises(ValueError):
        build_subject("", "heartbeat", "runner-001")


class _FakeJetStream:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes]] = []

    async def publish(self, subject: str, payload: bytes) -> None:
        self.published.append((subject, payload))


class _FakeCore:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes]] = []

    async def publish(self, subject: str, payload: bytes) -> None:
        self.published.append((subject, payload))

    async def drain(self) -> None:
        pass


def _envelope() -> NatsEnvelope:
    return NatsEnvelope(
        event_id="00000000-0000-0000-0000-000000000001",
        tenant_id="acme",
        occurred_at="2026-06-25T10:00:00.000000000Z",
        payload={"event_type": "OrderFillReport", "order_id": "o1"},
        ordering=OrderingMeta(session_id="s1", seq=1),
    )


@pytest.mark.asyncio
async def test_publish_telemetry_envelope_goes_to_jetstream_when_connected():
    client = ArxNatsClient(nats_url="nats://localhost:4222", tenant_id="acme", runner_id="r1")
    js = _FakeJetStream()
    client._js = js  # type: ignore[attr-defined]
    client._nc = _FakeCore()  # type: ignore[attr-defined]
    await client.publish_telemetry_envelope(
        "arx.acme.telemetry.r1.s1", _envelope()
    )
    assert len(js.published) == 1
    subject, payload = js.published[0]
    assert subject == "arx.acme.telemetry.r1.s1"
    assert b"OrderFillReport" in payload


@pytest.mark.asyncio
async def test_publish_fire_and_forget_uses_core_not_jetstream():
    client = ArxNatsClient(nats_url="nats://localhost:4222", tenant_id="acme", runner_id="r1")
    core = _FakeCore()
    client._nc = core  # type: ignore[attr-defined]
    await client.publish_fire_and_forget("arx.acme.heartbeat.r1", b"ping")
    assert core.published == [("arx.acme.heartbeat.r1", b"ping")]


@pytest.mark.asyncio
async def test_publish_fire_and_forget_silently_noops_when_disconnected():
    client = ArxNatsClient(nats_url="nats://localhost:4222", tenant_id="acme", runner_id="r1")
    # No fake _nc → simulate disconnection.
    await client.publish_fire_and_forget("arx.acme.heartbeat.r1", b"ping")
    # No exception, no buffer growth — heartbeat is at-most-once by design.


@pytest.mark.asyncio
async def test_wal_stashes_telemetry_while_disconnected_and_drains_on_connect(tmp_path: Path):
    wal_file = tmp_path / "wal.db"
    client = ArxNatsClient(
        nats_url="nats://localhost:4222",
        tenant_id="acme",
        runner_id="r1",
        wal_path=wal_file,
    )

    # Disconnected publish → goes to WAL.
    await client.publish_telemetry_envelope(
        "arx.acme.telemetry.r1.s1", _envelope()
    )
    assert wal_file.exists()

    # Reconnect: install fake jetstream, run the private drain.
    js = _FakeJetStream()
    client._js = js  # type: ignore[attr-defined]
    await client._drain_wal()  # type: ignore[attr-defined]

    assert len(js.published) == 1
    subject, payload = js.published[0]
    assert subject == "arx.acme.telemetry.r1.s1"
    assert b"OrderFillReport" in payload

    # WAL should be empty after drain.
    await client._drain_wal()  # type: ignore[attr-defined]
    assert len(js.published) == 1, "second drain must not re-publish"

    client._wal.close()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_wal_replays_in_fifo_order(tmp_path: Path):
    wal_file = tmp_path / "wal.db"
    client = ArxNatsClient(
        nats_url="nats://localhost:4222",
        tenant_id="acme",
        runner_id="r1",
        wal_path=wal_file,
    )

    # Stash three messages while disconnected, with distinct subjects.
    for i in range(3):
        env = NatsEnvelope(
            event_id=f"00000000-0000-0000-0000-00000000000{i}",
            tenant_id="acme",
            occurred_at="2026-06-25T10:00:00.000000000Z",
            payload={"order_id": f"o{i}"},
            ordering=OrderingMeta(session_id="s1", seq=i + 1),
        )
        await client.publish_telemetry_envelope(
            f"arx.acme.telemetry.r1.s1.msg-{i}", env
        )

    js = _FakeJetStream()
    client._js = js  # type: ignore[attr-defined]
    await client._drain_wal()  # type: ignore[attr-defined]

    subjects = [s for s, _ in js.published]
    assert subjects == [
        "arx.acme.telemetry.r1.s1.msg-0",
        "arx.acme.telemetry.r1.s1.msg-1",
        "arx.acme.telemetry.r1.s1.msg-2",
    ]
    client._wal.close()  # type: ignore[attr-defined]
