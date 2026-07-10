"""Periodic state snapshot publisher.

Polls the execution engine's Tier-2 observability methods
(``get_positions`` / ``get_orders`` / ``get_engine_status``) at a fixed
cadence and publishes a Decimal-safe envelope to
``arx.{tenant}.snapshot.state.{runner_id}.{spec_id}``. The wire format is
``str(Decimal)`` for every money field (red line 0.4).

The publish path is JetStream-backed via ``publish_telemetry_envelope`` so a
disconnected snapshot is stashed in the offline WAL and replayed on the next
successful connect (at-least-once, plan-index §6). Silent drops are
prevented by the client's WAL stash + structured logs (audit-not-silent
invariant, lesson #21).

The publish path is engine-agnostic — the publisher only sees the Tier-2
snapshot protocol, so a future engine (hummingbot / freqtrade / …) that
implements the same Tier-2 surface is observed automatically.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

import uuid6

from custos.core.engine_protocol import EngineStatus, OrderSnapshot, PositionSnapshot
from custos.core.log import get_logger
from custos.core.nats_client import NatsEnvelope, build_subject

_log = get_logger("custos.state_snapshot")

# 10 seconds is a conservative default — frequent enough for the arx UI to
# feel live without saturating the NATS uplink. Operators tune via the
# constructor arg; there is no cloud-side override yet.
_DEFAULT_INTERVAL_SECS = 10.0


class _NatsPublisher(Protocol):
    """Structural subtype of ``ArxNatsClient`` used by the publisher.

    ``publish_telemetry_envelope`` is JetStream-backed with WAL stash on
    disconnect (at-least-once). The publisher must not synthesise its own
    envelope-to-bytes path — the client owns transport, the publisher only
    owns the payload schema."""

    async def publish_telemetry_envelope(self, subject: str, envelope: NatsEnvelope) -> None: ...


class _SnapshotEngine(Protocol):
    """The subset of ``ExecutionEngineProtocol`` the publisher needs.

    Using a narrower protocol keeps the publisher trivially unit-testable
    with a stub engine — a full ``ExecutionEngineProtocol`` implementation
    would require Tier-1 lifecycle machinery irrelevant here."""

    async def get_positions(self, spec_id: str) -> list[PositionSnapshot]: ...

    async def get_orders(self, spec_id: str) -> list[OrderSnapshot]: ...

    async def get_engine_status(self, spec_id: str) -> EngineStatus: ...


def _position_to_wire(snapshot: PositionSnapshot) -> dict:
    return {
        "instrument_id": snapshot.instrument_id,
        "quantity": str(snapshot.quantity),
        "avg_px": str(snapshot.avg_px),
        "unrealized_pnl": str(snapshot.unrealized_pnl),
        "notional": str(snapshot.notional),
    }


def _order_to_wire(snapshot: OrderSnapshot) -> dict:
    return {
        "client_order_id": snapshot.client_order_id,
        "instrument_id": snapshot.instrument_id,
        "side": snapshot.side,
        "quantity": str(snapshot.quantity),
        "price": str(snapshot.price),
        "status": snapshot.status,
    }


def _engine_status_to_wire(status: EngineStatus) -> dict:
    return {
        "phase": status.phase,
        "position_count": status.position_count,
        "order_count": status.order_count,
        "open_notional": str(status.open_notional),
        "peak_equity": str(status.peak_equity),
        "current_equity": str(status.current_equity),
        "drawdown_pct": str(status.drawdown_pct),
    }


def _now_rfc3339_nanos() -> str:
    """Match the ``NatsEnvelope`` occurred_at format (plan-index §6)."""

    ns = time.time_ns()
    secs, ns_rem = divmod(ns, 1_000_000_000)
    tm = time.gmtime(secs)
    return (
        f"{tm.tm_year:04d}-{tm.tm_mon:02d}-{tm.tm_mday:02d}"
        f"T{tm.tm_hour:02d}:{tm.tm_min:02d}:{tm.tm_sec:02d}.{ns_rem:09d}Z"
    )


@dataclass
class StateSnapshotPublisher:
    """Polls an engine's Tier-2 snapshot surface and pushes a JSON envelope
    over NATS. ``publish_once`` is exposed for deterministic unit tests;
    ``run`` is the production loop."""

    engine: _SnapshotEngine
    nats_client: _NatsPublisher
    tenant_id: str
    runner_id: str
    interval_secs: float = _DEFAULT_INTERVAL_SECS
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.interval_secs <= 0:
            raise ValueError("interval_secs must be > 0")

    def _subject(self, spec_id: str) -> str:
        # Lesson #26: routing through build_subject rejects empty tenant /
        # runner / spec ids so a typo can't silently route to
        # ``arx.tenant.snapshot.state..``.
        return build_subject(self.tenant_id, "snapshot", "state", self.runner_id, spec_id)

    async def publish_once(self, spec_id: str) -> None:
        """One tick: probe the engine, assemble the payload, publish. A
        probe exception is logged and the tick is skipped — the loop keeps
        running so a transient engine outage does not stop observability
        forever (autonomy, red line 0.3)."""

        try:
            positions = await self.engine.get_positions(spec_id)
            orders = await self.engine.get_orders(spec_id)
            engine_status = await self.engine.get_engine_status(spec_id)
        except Exception as exc:  # noqa: BLE001 — probe failure must not kill the publisher loop
            _log.warning(
                "state_snapshot_probe_failed",
                spec_id=spec_id,
                error=str(exc),
            )
            return

        payload = {
            "runner_id": self.runner_id,
            "spec_id": spec_id,
            "positions": [_position_to_wire(p) for p in positions],
            "orders": [_order_to_wire(o) for o in orders],
            "engine_status": _engine_status_to_wire(engine_status),
        }
        envelope = NatsEnvelope(
            event_id=str(uuid6.uuid7()),
            tenant_id=self.tenant_id,
            occurred_at=_now_rfc3339_nanos(),
            payload=payload,
            payload_schema_version=self.schema_version,
        )
        subject = self._subject(spec_id)
        try:
            await self.nats_client.publish_telemetry_envelope(subject, envelope)
        except Exception as exc:  # noqa: BLE001 — publish failure must not kill the loop
            _log.warning(
                "state_snapshot_publish_failed",
                subject=subject,
                error=str(exc),
            )

    async def run(
        self,
        stop: asyncio.Event,
        spec_id_source: Callable[[], Sequence[str]],
    ) -> None:
        """Publish every ``interval_secs`` until ``stop`` is set. The set of
        spec ids to snapshot is re-read from ``spec_id_source`` on each tick,
        so specs deployed / undeployed by the reconciler after startup are
        picked up without re-spawning the publisher."""

        _log.info(
            "state_snapshot_publisher_started",
            tenant_id=self.tenant_id,
            runner_id=self.runner_id,
            interval_secs=self.interval_secs,
        )
        while not stop.is_set():
            for spec_id in spec_id_source():
                await self.publish_once(spec_id)
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval_secs)
            except TimeoutError:
                continue
        _log.info(
            "state_snapshot_publisher_stopped",
            tenant_id=self.tenant_id,
            runner_id=self.runner_id,
        )
