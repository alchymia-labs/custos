"""Telemetry actor — bridges the NautilusTrader MessageBus to the NATS
phone-home channel.

We don't import nautilus_trader at module load time because the runner is
shipped without it in CI / unit-test environments — the actor is driven
through `on_event(name, payload)` whether the source is the real NT
MessageBus or a fake. Production code wires `on_event` to
`MessageBus.subscribe()` callbacks at startup; tests call it directly.

The actor enforces a schema whitelist (only event names declared at
construction time leak out to NATS), batches events through an
asyncio.Queue + periodic flush, and stamps each outgoing message with a
monotonic seq within a single session_id (a fresh session_id is minted on
on_start so a runner restart forces the consumer-side watermark to
re-reconcile — domain-model §1 ③).
"""

from __future__ import annotations

import asyncio
import time

import uuid6
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from arx_runner.nats_client import (
    ArxNatsClient,
    NatsEnvelope,
    OrderingMeta,
    _now_rfc3339_nanos,
)


class TelemetryPublisher(Protocol):
    """Minimal contract for the NATS client side. Real client is
    `ArxNatsClient`; tests inject a stub that records published bytes.
    """

    async def publish_telemetry(self, *, session_id: str, envelope: NatsEnvelope) -> None: ...

    async def publish_heartbeat_fire_and_forget(
        self, *, session_id: str, envelope: NatsEnvelope
    ) -> None: ...


@dataclass(frozen=True)
class TelemetryActorConfig:
    """Knobs for the actor. `allowed_event_types` is the schema whitelist
    — only matching events are forwarded; everything else is silently
    dropped (so adding a new NT event type does not accidentally leak
    PII before the operator opts in)."""

    allowed_event_types: frozenset[str]
    batch_size: int = 50
    flush_interval_secs: float = 1.0
    heartbeat_interval_secs: float = 10.0


@dataclass
class TelemetryActor:
    """NT MessageBus subscriber that buffers events and publishes them to
    NATS in batches. Construct with the publisher + identity + config,
    call `start()` to spin up the flush + heartbeat loops, push events
    via `on_event()`, and call `stop()` to drain and shut down."""

    publisher: TelemetryPublisher
    tenant_id: str
    runner_id: str
    config: TelemetryActorConfig
    # Time-ordered session_id (UUIDv7) — consumer-side watermark relies
    # on the embedded 48-bit unix_ts_ms prefix to compare sessions.
    session_id: str = field(default_factory=lambda: str(uuid6.uuid7()))
    _seq: int = 0
    _heartbeat_seq: int = 0
    _started_at: float = field(default_factory=time.monotonic)
    _queue: asyncio.Queue[NatsEnvelope] = field(default_factory=asyncio.Queue)
    _flush_task: asyncio.Task[None] | None = None
    _heartbeat_task: asyncio.Task[None] | None = None
    _stopping: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        if self.config.batch_size < 1:
            raise ValueError("batch_size must be >= 1")

    def active_deployment_count(self) -> int:
        """Best-effort current active deployment count for heartbeat
        payloads. v1 returns 0 — the NT host binding plan will surface
        the real count from the engine session."""
        return 0

    # ------------------------------------------------------------------
    # NT MessageBus hooks (called by `MessageBus.subscribe()` callbacks
    # or directly by tests).
    # ------------------------------------------------------------------

    def on_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Synchronous fast path called from the NT MessageBus thread.
        Filters by whitelist, stamps with ordering metadata, and enqueues
        for the async flush loop. Never raises — a malformed event must
        not crash the trading loop."""
        if event_type not in self.config.allowed_event_types:
            return
        self._seq += 1
        envelope = NatsEnvelope(
            event_id=str(uuid6.uuid7()),
            tenant_id=self.tenant_id,
            occurred_at=_now_rfc3339_nanos(),
            payload={"event_type": event_type, **payload},
            ordering=OrderingMeta(session_id=self.session_id, seq=self._seq),
        )
        # `put_nowait` is safe because asyncio.Queue defaults to unbounded;
        # if we ever bound it, treat full-queue as fail-fast logging, not silent drop.
        self._queue.put_nowait(envelope)

    async def start(self) -> None:
        if self._flush_task is not None:
            raise RuntimeError("TelemetryActor already started")
        self._stopping.clear()
        loop = asyncio.get_running_loop()
        self._flush_task = loop.create_task(self._flush_loop(), name="telemetry-flush")
        self._heartbeat_task = loop.create_task(
            self._heartbeat_loop(), name="telemetry-heartbeat"
        )

    async def stop(self) -> None:
        self._stopping.set()
        # Drain remaining queue items before cancelling — at-least-once
        # semantics demand we don't drop buffered telemetry on shutdown.
        await self._drain_queue()
        for task in (self._flush_task, self._heartbeat_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
        self._flush_task = None
        self._heartbeat_task = None

    # ------------------------------------------------------------------
    # Internal loops
    # ------------------------------------------------------------------

    async def _flush_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await asyncio.wait_for(
                    self._wait_for_batch_or_interval(),
                    timeout=self.config.flush_interval_secs,
                )
            except asyncio.TimeoutError:
                pass
            await self._drain_batch()

    async def _wait_for_batch_or_interval(self) -> None:
        # Wake up as soon as we have at least `batch_size` items queued.
        while self._queue.qsize() < self.config.batch_size:
            await asyncio.sleep(0.01)

    async def _drain_batch(self) -> None:
        sent = 0
        while sent < self.config.batch_size and not self._queue.empty():
            env = self._queue.get_nowait()
            await self.publisher.publish_telemetry(
                session_id=self.session_id, envelope=env
            )
            sent += 1

    async def _drain_queue(self) -> None:
        while not self._queue.empty():
            env = self._queue.get_nowait()
            await self.publisher.publish_telemetry(
                session_id=self.session_id, envelope=env
            )

    async def _heartbeat_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await asyncio.wait_for(
                    self._stopping.wait(), timeout=self.config.heartbeat_interval_secs
                )
            except asyncio.TimeoutError:
                await self._send_heartbeat()

    async def _send_heartbeat(self) -> None:
        self._heartbeat_seq += 1
        envelope = NatsEnvelope(
            event_id=str(uuid6.uuid7()),
            tenant_id=self.tenant_id,
            occurred_at=_now_rfc3339_nanos(),
            payload={
                "runner_id": self.runner_id,
                "uptime_secs": int(time.monotonic() - self._started_at),
                "active_deployments": self.active_deployment_count(),
                "health": "online",
            },
            ordering=OrderingMeta(
                session_id=self.session_id, seq=self._heartbeat_seq
            ),
        )
        await self.publisher.publish_heartbeat_fire_and_forget(
            session_id=self.session_id, envelope=envelope
        )


# ----------------------------------------------------------------------
# Adapter — wraps the real ArxNatsClient as a TelemetryPublisher.
# ----------------------------------------------------------------------


@dataclass
class ArxNatsTelemetryAdapter:
    """Bridges TelemetryActor (which speaks `NatsEnvelope`) to
    ArxNatsClient (which owns the actual NATS connection). Kept as a
    thin wrapper so tests can drop in a fake without dragging the full
    NATS connection contract."""

    client: ArxNatsClient

    async def publish_telemetry(self, *, session_id: str, envelope: NatsEnvelope) -> None:
        subject = f"arx.{self.client.tenant_id}.telemetry.{self.client.runner_id}.{session_id}"
        await self.client.publish_telemetry_envelope(subject, envelope)

    async def publish_heartbeat_fire_and_forget(
        self, *, session_id: str, envelope: NatsEnvelope
    ) -> None:
        subject = f"arx.{self.client.tenant_id}.heartbeat.{self.client.runner_id}"
        await self.client.publish_fire_and_forget(subject, envelope.to_bytes())


# Re-export for callers wiring NT MessageBus into the actor.
SubscribeCallback = Callable[[dict[str, Any]], Awaitable[None]]
