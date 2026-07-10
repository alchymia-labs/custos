"""State snapshot publisher contract.

The periodic publisher polls the execution engine's Tier-2 snapshot methods
(get_positions / get_orders / get_engine_status) and pushes a Decimal-safe
payload to ``arx.{tenant}.snapshot.state.{runner_id}``. The wire format is
``str(Decimal)`` for every money field (red line 0.4). When the underlying
NATS client is disconnected the publisher relies on WAL / fire-and-forget
semantics rather than dropping silently.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal

from custos.core.engine_protocol import EngineStatus, OrderSnapshot, PositionSnapshot
from custos.core.state_snapshot import StateSnapshotPublisher


class _StubEngine:
    """A minimal ``ExecutionEngineProtocol`` stub — just the Tier-2 snapshot
    methods used by the publisher. Positions carry Decimal money so we can
    prove wire serialisation stays Decimal-safe."""

    def __init__(self) -> None:
        self._positions = [
            PositionSnapshot(
                instrument_id="BTCUSDT",
                quantity=Decimal("1.5"),
                avg_px=Decimal("100.25"),
                unrealized_pnl=Decimal("5"),
                notional=Decimal("150.375"),
            )
        ]
        self._orders = [
            OrderSnapshot(
                client_order_id="c1",
                instrument_id="BTCUSDT",
                side="BUY",
                quantity=Decimal("0.5"),
                price=Decimal("99.5"),
                status="ACCEPTED",
            )
        ]
        self._status = EngineStatus(
            phase="running",
            position_count=1,
            order_count=1,
            open_notional=Decimal("150.375"),
            peak_equity=Decimal("200"),
            current_equity=Decimal("180"),
            drawdown_pct=Decimal("10"),
        )

    async def get_positions(self, spec_id: str) -> list[PositionSnapshot]:
        return list(self._positions)

    async def get_orders(self, spec_id: str) -> list[OrderSnapshot]:
        return list(self._orders)

    async def get_engine_status(self, spec_id: str) -> EngineStatus:
        return self._status


class _CapturingNatsClient:
    """A NATS client fake capturing every fire-and-forget publish so the
    contract can inspect subject + payload without a running broker."""

    def __init__(self) -> None:
        self.published: list[tuple[str, bytes]] = []

    async def publish_fire_and_forget(self, subject: str, payload: bytes) -> None:
        self.published.append((subject, payload))


class _DisconnectedNatsClient:
    """Simulates a disconnected client that logs a no-op (fire-and-forget
    semantics) rather than raising. Records calls so the test can assert
    the publisher still tried to publish (no silent drop by the publisher)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def publish_fire_and_forget(self, subject: str, payload: bytes) -> None:
        # Real ArxNatsClient logs ``nats_fire_and_forget_noop_disconnected``
        # and returns. The publisher must not raise on this.
        self.calls.append(subject)


async def test_state_snapshot_publishes_str_decimal_money() -> None:
    engine = _StubEngine()
    client = _CapturingNatsClient()
    publisher = StateSnapshotPublisher(
        engine=engine,
        nats_client=client,
        tenant_id="tenant-a",
        runner_id="runner-1",
        interval_secs=0.01,
    )

    await publisher.publish_once(spec_id="spec-1")

    assert len(client.published) == 1
    subject, payload = client.published[0]
    # Subject shape per lesson #26: build_subject(tenant, "snapshot", "state",
    # runner, spec). We only assert the leading anchors so the exact tail is
    # a design decision the publisher owns.
    assert subject.startswith("arx.tenant-a.snapshot.state.")
    body = json.loads(payload)
    # Every money field on the wire is a JSON string, never a float — this
    # is the red line 0.4 wire contract.
    engine_status = body["payload"]["engine_status"]
    for field_name in ("open_notional", "peak_equity", "current_equity", "drawdown_pct"):
        assert isinstance(engine_status[field_name], str), field_name
        # str(Decimal) never round-trips through float.
        Decimal(engine_status[field_name])
    position_wire = body["payload"]["positions"][0]
    for field_name in ("quantity", "avg_px", "unrealized_pnl", "notional"):
        assert isinstance(position_wire[field_name], str), field_name
    order_wire = body["payload"]["orders"][0]
    for field_name in ("quantity", "price"):
        assert isinstance(order_wire[field_name], str), field_name


async def test_state_snapshot_periodic_interval_respected() -> None:
    engine = _StubEngine()
    client = _CapturingNatsClient()
    publisher = StateSnapshotPublisher(
        engine=engine,
        nats_client=client,
        tenant_id="tenant-a",
        runner_id="runner-1",
        interval_secs=0.05,
    )
    stop = asyncio.Event()

    # Run for slightly more than 2 intervals (~0.12s), then stop.
    task = asyncio.create_task(publisher.run(stop=stop, spec_id="spec-1"))
    await asyncio.sleep(0.12)
    stop.set()
    await asyncio.wait_for(task, timeout=1.0)

    # Expect ~2-3 publishes over 0.12s at 0.05s cadence — assert >= 2 to
    # tolerate scheduler jitter without letting the test become vacuous.
    assert len(client.published) >= 2
    # Cadence: successive subject payloads must be distinct events (event_id
    # is a UUIDv7 that only advances forward).
    ids = [json.loads(payload)["event_id"] for _subj, payload in client.published]
    assert len(set(ids)) == len(ids)


async def test_snapshot_cached_when_disconnected() -> None:
    """When the NATS client is disconnected (fire-and-forget no-op semantics),
    the publisher continues invoking publish so downstream WAL / logging can
    surface the disconnect. Silent-drop by the publisher itself would violate
    the audit-not-silent invariant (lesson #21). Real disconnect handling
    lives in the client."""

    engine = _StubEngine()
    client = _DisconnectedNatsClient()
    publisher = StateSnapshotPublisher(
        engine=engine,
        nats_client=client,
        tenant_id="tenant-a",
        runner_id="runner-1",
        interval_secs=0.01,
    )

    await publisher.publish_once(spec_id="spec-1")

    assert client.calls, "publisher must invoke publish even when disconnected"


async def test_state_snapshot_survives_engine_probe_exception() -> None:
    """A snapshot probe failure must not crash the loop (red line 0.3 —
    autonomy). Publisher logs + skips one tick, ready for the next."""

    class _ExplodingEngine:
        async def get_positions(self, spec_id: str) -> list[PositionSnapshot]:
            raise RuntimeError("simulated engine outage")

        async def get_orders(self, spec_id: str) -> list[OrderSnapshot]:
            return []

        async def get_engine_status(self, spec_id: str) -> EngineStatus:
            return EngineStatus(
                phase="running",
                position_count=0,
                order_count=0,
                open_notional=Decimal("0"),
                peak_equity=Decimal("0"),
                current_equity=Decimal("0"),
                drawdown_pct=Decimal("0"),
            )

    client = _CapturingNatsClient()
    publisher = StateSnapshotPublisher(
        engine=_ExplodingEngine(),  # type: ignore[arg-type]
        nats_client=client,
        tenant_id="tenant-a",
        runner_id="runner-1",
        interval_secs=0.01,
    )

    # Must not raise, must not publish an incomplete snapshot.
    await publisher.publish_once(spec_id="spec-1")
    assert client.published == []


def test_state_snapshot_module_exports_publisher() -> None:
    """The module surface is ``StateSnapshotPublisher`` — no accidental
    private-name leaks that would break at import time."""

    from custos.core import state_snapshot

    assert hasattr(state_snapshot, "StateSnapshotPublisher")
