"""Telemetry actor — bridges the NautilusTrader MessageBus to the NATS
phone-home channel.

We don't import nautilus_trader at module load time because the runner is
shipped without it in CI / unit-test environments — the actor is driven
through `on_event(name, payload)` whether the source is the real NT
MessageBus or a fake. Production code wires `on_event` to
`MessageBus.subscribe()` callbacks at startup; tests call it directly.

The actor enforces a schema whitelist (only event names declared at
construction time leak out to NATS), batches events through a bounded
asyncio.Queue + periodic flush, and stamps each outgoing message with a
monotonic seq within a single session_id (a fresh session_id is minted on
on_start so a runner restart forces the consumer-side watermark to
re-reconcile — domain-model §1 ③).

Cross-thread safety: ``on_event`` runs on whatever thread the NT
MessageBus dispatches from; the queue lives on the asyncio loop. The
actor uses ``loop.call_soon_threadsafe`` to hand off envelopes safely and
serialises seq mutation behind a ``threading.Lock`` so two concurrent
callbacks never produce duplicate or out-of-order seq numbers.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import uuid6

from arx_runner.config import TelemetryQueueConfig
from arx_runner.log import get_logger
from arx_runner.nats_client import (
    ArxNatsClient,
    NatsEnvelope,
    OrderingMeta,
    _now_rfc3339_nanos,
    build_subject,
)

_log = get_logger("arx_runner.telemetry_actor")


# Money-field names that must arrive as ``str(Decimal)`` (or ``int``) at the
# telemetry boundary. ``float`` is structurally lossy — binary fractions
# silently corrupt the differential-test invariant against the Crucible
# Python reference (ADR-008 red line). Extend this set when a new money
# field joins the wire envelope; the rejection is fail-fast so a producer
# regression cannot leak floats past this gate.
MONEY_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "equity",
        "qty",
        "price",
        "pnl",
        "notional",
        "amount",
        "source_amount",
        "target_amount",
        "hwm_equity",
        "current_equity",
        "day_start_equity",
        "drawdown_pct",
        "daily_loss",
        "cumulative_pnl",
        "fee",
    }
)

# NT event class names the telemetry bridge forwards. Order fills and position
# lifecycle events are the trading footprint the cloud needs (domain-model §1.5
# summary uplink); OrderDenied is deliberately absent — a denial rides the
# separate pre_trade_reject subject via NtRiskEngineBridge, not the telemetry
# channel. The set doubles as the actor's schema whitelist so a drifting NT
# event name cannot silently start (or stop) leaking.
TELEMETRY_ORDER_EVENT_TYPES: frozenset[str] = frozenset({"OrderFilled"})
TELEMETRY_POSITION_EVENT_TYPES: frozenset[str] = frozenset(
    {"PositionOpened", "PositionChanged", "PositionClosed"}
)
DEFAULT_TELEMETRY_EVENT_TYPES: frozenset[str] = (
    TELEMETRY_ORDER_EVENT_TYPES | TELEMETRY_POSITION_EVENT_TYPES
)


class MoneyFieldFloatRejected(TypeError):
    """Raised when a money-typed field arrives as ``float`` (or ``bool``).

    Money values must be supplied as ``str(Decimal(...))`` so the wire
    representation is exact and the differential-test contract holds.
    """

    def __init__(self, field_name: str, value: object) -> None:
        super().__init__(
            f"telemetry money field {field_name!r} arrived as "
            f"{type(value).__name__}={value!r}; use str(Decimal(...))"
        )
        self.field_name = field_name
        self.value = value


def _reject_floats_in_money_fields(event_type: str, payload: dict[str, Any]) -> None:
    """Raise ``MoneyFieldFloatRejected`` on the first money field carrying a
    ``float``. ``bool`` is a ``float`` subclass and is rejected too — a
    ``True`` slipping through would round-trip as ``1.0``."""
    for key, value in payload.items():
        if key not in MONEY_FIELD_NAMES:
            continue
        # bool is checked explicitly because ``isinstance(True, float)`` is
        # False but ``isinstance(True, int)`` is True — the int-allowed
        # branch below would let bools through otherwise.
        if isinstance(value, bool) or isinstance(value, float):
            _log.error(
                "telemetry_money_field_float_rejected",
                event_type=event_type,
                field=key,
                value_type=type(value).__name__,
            )
            raise MoneyFieldFloatRejected(key, value)


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
    """Knobs for the actor. ``allowed_event_types`` is the schema whitelist
    — only matching events are forwarded; everything else is dropped at
    the boundary (so adding a new NT event type does not accidentally
    leak PII before the operator opts in). ``queue`` bounds the in-process
    buffer + per-publish batch size."""

    allowed_event_types: frozenset[str]
    batch_size: int = 50
    flush_interval_secs: float = 1.0
    heartbeat_interval_secs: float = 10.0
    queue: TelemetryQueueConfig = field(default_factory=TelemetryQueueConfig)


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
    _seq_lock: threading.Lock = field(default_factory=threading.Lock)
    _heartbeat_seq: int = 0
    _drop_counter: int = 0
    _started_at: float = field(default_factory=time.monotonic)
    _queue: asyncio.Queue[NatsEnvelope] = field(init=False)
    _flush_task: asyncio.Task[None] | None = None
    _heartbeat_task: asyncio.Task[None] | None = None
    _stopping: asyncio.Event = field(default_factory=asyncio.Event)
    _loop: asyncio.AbstractEventLoop | None = None

    def __post_init__(self) -> None:
        if self.config.batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if self.config.queue.max_queue_size < 1:
            raise ValueError("max_queue_size must be >= 1")
        self._queue = asyncio.Queue(maxsize=self.config.queue.max_queue_size)

    def active_deployment_count(self) -> int:
        """Best-effort current active deployment count for heartbeat
        payloads. v1 returns 0 — the NT host binding will surface the real
        count from the engine session in a later integration step."""
        return 0

    def drop_count(self) -> int:
        """Total envelopes dropped due to queue overflow. Hook for ops
        metrics."""
        return self._drop_counter

    # ------------------------------------------------------------------
    # NT MessageBus hooks (called by `MessageBus.subscribe()` callbacks
    # or directly by tests).
    # ------------------------------------------------------------------

    def on_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Synchronous fast path called from the NT MessageBus thread.
        Filters by whitelist, runs the money-field contract gate, stamps
        with ordering metadata, and enqueues for the async flush loop.

        Raises :class:`MoneyFieldFloatRejected` if a money field arrives as
        ``float`` or ``bool`` — fail-fast is intentional so a producer
        regression cannot corrupt the wire (ADR-008 red line). Other
        validation errors are not raised; the trading loop must keep
        running. Cross-thread safe: seq mutation runs under a lock and the
        queue handoff goes through ``call_soon_threadsafe``."""
        if event_type not in self.config.allowed_event_types:
            _log.debug(
                "telemetry_event_dropped_whitelist",
                event_type=event_type,
                reason="not_in_allowlist",
            )
            return

        # Money-field contract gate. Floats / bools in money fields raise
        # before the envelope is built so a buggy producer cannot smuggle
        # binary fractions onto the wire (ADR-008 red line). The raise is
        # intentional fail-fast — the trading loop should refuse to publish
        # corrupt money values rather than continue silently.
        _reject_floats_in_money_fields(event_type, payload)

        with self._seq_lock:
            self._seq += 1
            seq = self._seq

        envelope = NatsEnvelope(
            event_id=str(uuid6.uuid7()),
            tenant_id=self.tenant_id,
            occurred_at=_now_rfc3339_nanos(),
            payload={"event_type": event_type, **payload},
            ordering=OrderingMeta(session_id=self.session_id, seq=seq),
        )

        if self._loop is not None and not self._loop_is_current():
            # NT thread → hand off to the asyncio loop thread-safely.
            self._loop.call_soon_threadsafe(self._try_enqueue, envelope, event_type)
        else:
            # Same thread (e.g. tests calling on_event from the loop) →
            # direct enqueue is safe.
            self._try_enqueue(envelope, event_type)

    def _loop_is_current(self) -> bool:
        """True iff we're currently executing inside the actor's loop.
        Returns False when there is no running loop (NT MessageBus
        thread)."""
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            return False
        return running is self._loop

    def _try_enqueue(self, envelope: NatsEnvelope, event_type: str) -> None:
        """Enqueue or drop-newest with structured log + counter increment."""
        try:
            self._queue.put_nowait(envelope)
        except asyncio.QueueFull:
            self._drop_counter += 1
            _log.warning(
                "telemetry_event_dropped_queue_full",
                event_type=event_type,
                reason="queue_full",
                drop_count_total=self._drop_counter,
                max_queue_size=self.config.queue.max_queue_size,
            )

    async def start(self) -> None:
        if self._flush_task is not None:
            raise RuntimeError("TelemetryActor already started")
        self._stopping.clear()
        self._loop = asyncio.get_running_loop()
        self._flush_task = self._loop.create_task(self._flush_loop(), name="telemetry-flush")
        self._heartbeat_task = self._loop.create_task(
            self._heartbeat_loop(), name="telemetry-heartbeat"
        )

    async def stop(self) -> None:
        """Stop in a strict order: signal → cancel tasks → await → final
        drain. Cancelling first prevents the flush loop from racing the
        drain. The final drain pulls anything still buffered so the
        at-least-once promise holds across shutdown."""
        self._stopping.set()

        for task in (self._flush_task, self._heartbeat_task):
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001 — capture stop-time crashes
                _log.error(
                    "telemetry_actor_task_died_during_stop",
                    task=task.get_name(),
                    error=str(exc),
                )

        self._flush_task = None
        self._heartbeat_task = None
        # Drain remaining queue items after cancellation so we don't drop
        # buffered telemetry on shutdown.
        await self._drain_queue()

    # ------------------------------------------------------------------
    # Internal loops
    # ------------------------------------------------------------------

    async def _flush_loop(self) -> None:
        """Block on queue.get() for the first envelope, then drain to a
        configurable batch ceiling. No polling sleep — the loop wakes the
        instant an envelope arrives."""
        while not self._stopping.is_set():
            try:
                first = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=self.config.flush_interval_secs,
                )
            except TimeoutError:
                # Heartbeat tick — nothing to flush, just loop.
                continue
            await self._drain_batch_starting_with(first)

    async def _drain_batch_starting_with(self, first: NatsEnvelope) -> None:
        """Publish ``first`` then drain whatever else is queued, up to the
        per-publish batch ceiling. Survives publish exceptions: a failure
        logs + counts but the flush task keeps running (JetStream
        redelivery handles at-least-once)."""
        batch_cap = self.config.queue.max_batch_size_per_publish
        envelopes: list[NatsEnvelope] = [first]
        while len(envelopes) < batch_cap:
            try:
                envelopes.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        for env in envelopes:
            try:
                await self.publisher.publish_telemetry(session_id=self.session_id, envelope=env)
            except Exception as exc:  # noqa: BLE001 — survive publish errors
                self._drop_counter += 1
                _log.error(
                    "telemetry_publish_failed",
                    event_id=env.event_id,
                    seq=env.ordering.seq if env.ordering else None,
                    error=str(exc),
                )

    async def _drain_queue(self) -> None:
        """Single-threaded final drain run after the flush loop is
        cancelled in ``stop()``. Same publish-survives-error guarantee as
        the in-flight flush — at-least-once relies on JetStream
        redelivery."""
        while True:
            try:
                env = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                await self.publisher.publish_telemetry(session_id=self.session_id, envelope=env)
            except Exception as exc:  # noqa: BLE001
                self._drop_counter += 1
                _log.error(
                    "telemetry_publish_failed_during_stop",
                    event_id=env.event_id,
                    error=str(exc),
                )

    async def _heartbeat_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await asyncio.wait_for(
                    self._stopping.wait(), timeout=self.config.heartbeat_interval_secs
                )
            except TimeoutError:
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
            ordering=OrderingMeta(session_id=self.session_id, seq=self._heartbeat_seq),
        )
        try:
            await self.publisher.publish_heartbeat_fire_and_forget(
                session_id=self.session_id, envelope=envelope
            )
        except Exception as exc:  # noqa: BLE001 — heartbeat must never crash the loop
            _log.warning(
                "heartbeat_publish_failed",
                seq=self._heartbeat_seq,
                error=str(exc),
            )


# ----------------------------------------------------------------------
# NT event → telemetry payload normalizers.
#
# NT serialises each event through ``type(event).to_dict(event)`` (a static
# method; the instance ``.to_dict()`` form raises). Quantity / Price fields
# come back as pure decimal strings; Money fields come back as
# ``"<decimal> <CCY>"``. Enums come back via ``*_to_str`` ("BUY"), never the
# raw ``str(OrderSide.BUY) == "1"``. The normalizers pick only string / int
# keys and split Money into a pure-decimal value + currency so the wire stays
# ``str(Decimal)`` with no float and no currency suffix (红线 0.4).
# ----------------------------------------------------------------------


def _split_money(money_str: str) -> tuple[str, str | None]:
    """Split an NT Money serialisation ``"<decimal> <CCY>"`` into its
    pure-decimal value and currency code. Quantity / Price serialise without a
    suffix, so only call this on Money-typed fields (commission / realized_pnl).
    """
    value, _, ccy = money_str.partition(" ")
    return value, (ccy or None)


def normalize_fill_event(event: Any) -> dict[str, Any]:
    """Summarise an NT ``OrderFilled`` for the telemetry channel. Money fields
    (``qty`` / ``price`` / ``fee``) are strings so the money-field gate passes
    them straight through."""
    d = type(event).to_dict(event)
    fee, fee_ccy = _split_money(d["commission"])
    return {
        "client_order_id": d["client_order_id"],
        "symbol": d["instrument_id"],
        "side": d["order_side"],
        "qty": d["last_qty"],
        "price": d["last_px"],
        "fee": fee,
        "fee_ccy": fee_ccy,
        "ts_event": d["ts_event"],
    }


def normalize_position_event(event: Any) -> dict[str, Any]:
    """Summarise an NT position lifecycle event (Opened / Changed / Closed).
    ``realized_pnl`` is a Money serialisation, split into ``pnl`` (pure decimal)
    + ``pnl_ccy`` so the wire money stays suffix-free."""
    d = type(event).to_dict(event)
    pnl, pnl_ccy = _split_money(d["realized_pnl"])
    return {
        "symbol": d["instrument_id"],
        "side": d["side"],
        "qty": d["quantity"],
        "pnl": pnl,
        "pnl_ccy": pnl_ccy,
        "ts_event": d["ts_event"],
    }


# ----------------------------------------------------------------------
# NT MessageBus → TelemetryActor bridge.
# ----------------------------------------------------------------------


@dataclass
class NtTelemetryBridge:
    """Subscribes to the NT MessageBus order + position event topics and
    forwards a money-safe summary of each whitelisted event into
    ``TelemetryActor.on_event``.

    NT publishes order events on ``events.order.{strategy_id}`` and position
    events on ``events.position.{strategy_id}`` (execution engine), so the
    bridge subscribes with the ``*`` wildcard tail and filters by event class
    name — a literal type-named topic would never match. Ducktyped over the
    MessageBus (no nautilus_trader import) so unit tests drive it without the
    engine.

    Handler exceptions are logged, never propagated: a telemetry hiccup must
    not crash the NT trading thread (non-custodial 红线 0.3). OrderDenied is
    intentionally not forwarded here — it rides the pre_trade_reject subject
    via ``NtRiskEngineBridge``.
    """

    actor: TelemetryActor

    def bootstrap(self, message_bus: Any | None) -> None:
        """Subscribe the bridge to the NT MessageBus. A missing bus is a
        fail-fast error surfaced loudly; the deploy-level attach guard catches
        it and degrades to observability loss rather than crashing the deploy
        (红线 0.3)."""
        if message_bus is None:
            _log.error("nt_messagebus_disconnected", runner_id=self.actor.runner_id)
            raise RuntimeError("NT MessageBus unavailable — cannot bootstrap telemetry bridge")
        message_bus.subscribe("events.order.*", self._on_order_event)
        message_bus.subscribe("events.position.*", self._on_position_event)
        _log.info("nt_telemetry_bridge_bootstrapped", runner_id=self.actor.runner_id)

    def _on_order_event(self, event: Any) -> None:
        event_type = type(event).__name__
        if event_type in TELEMETRY_ORDER_EVENT_TYPES:
            self._forward(event_type, event, normalize_fill_event)

    def _on_position_event(self, event: Any) -> None:
        event_type = type(event).__name__
        if event_type in TELEMETRY_POSITION_EVENT_TYPES:
            self._forward(event_type, event, normalize_position_event)

    def _forward(
        self,
        event_type: str,
        event: Any,
        normalizer: Callable[[Any], dict[str, Any]],
    ) -> None:
        try:
            payload = normalizer(event)
        except (KeyError, AttributeError, TypeError, ValueError) as exc:
            # NT event shape drift (renamed / dropped field) — skip this event
            # with a structured log rather than crash the trading thread.
            _log.warning("telemetry_event_shape_mismatch", event_type=event_type, error=str(exc))
            return
        try:
            self.actor.on_event(event_type, payload)
        except Exception as exc:  # noqa: BLE001 — 红线 0.3: never crash the NT engine thread
            _log.error("telemetry_forward_failed", event_type=event_type, error=str(exc))


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
        # F4/IN-NATS-1: route every publish-site subject through
        # build_subject so empty tokens raise instead of silently
        # producing malformed "arx.acme.telemetry.." subjects.
        subject = build_subject(
            self.client.tenant_id,
            "telemetry",
            self.client.runner_id,
            session_id,
        )
        await self.client.publish_telemetry_envelope(subject, envelope)

    async def publish_heartbeat_fire_and_forget(
        self, *, session_id: str, envelope: NatsEnvelope
    ) -> None:
        subject = build_subject(self.client.tenant_id, "heartbeat", self.client.runner_id)
        await self.client.publish_fire_and_forget(subject, envelope.to_bytes())


# Re-export for callers wiring NT MessageBus into the actor.
SubscribeCallback = Callable[[dict[str, Any]], Awaitable[None]]
