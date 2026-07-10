"""State snapshot publisher contract.

The periodic publisher polls the execution engine's Tier-2 snapshot methods
(get_positions / get_orders / get_engine_status) and pushes a Decimal-safe
envelope to ``arx.{tenant}.snapshot.state.{runner_id}.{spec_id}``. The wire
format is ``str(Decimal)`` for every money field (red line 0.4). Publish
rides JetStream via ``publish_telemetry_envelope`` so a disconnected
snapshot is WAL-stashed for at-least-once replay on the next connect.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path

from custos.core.engine_protocol import EngineStatus, OrderSnapshot, PositionSnapshot
from custos.core.nats_client import ArxNatsClient, NatsEnvelope
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
    """A NATS client fake capturing every JetStream publish so the contract
    can inspect subject + envelope without a running broker."""

    def __init__(self) -> None:
        self.published: list[tuple[str, NatsEnvelope]] = []

    async def publish_telemetry_envelope(self, subject: str, envelope: NatsEnvelope) -> None:
        self.published.append((subject, envelope))


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
    subject, envelope = client.published[0]
    # Subject shape per lesson #26: build_subject(tenant, "snapshot", "state",
    # runner, spec). We only assert the leading anchors so the exact tail is
    # a design decision the publisher owns.
    assert subject.startswith("arx.tenant-a.snapshot.state.")
    body = json.loads(envelope.to_bytes())
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
    task = asyncio.create_task(publisher.run(stop=stop, spec_id_source=lambda: ["spec-1"]))
    await asyncio.sleep(0.12)
    stop.set()
    await asyncio.wait_for(task, timeout=1.0)

    # Expect ~2-3 publishes over 0.12s at 0.05s cadence — assert >= 2 to
    # tolerate scheduler jitter without letting the test become vacuous.
    assert len(client.published) >= 2
    # Cadence: successive envelopes must be distinct events (event_id
    # is a UUIDv7 that only advances forward).
    ids = [envelope.event_id for _subj, envelope in client.published]
    assert len(set(ids)) == len(ids)


async def test_state_snapshot_wal_cached_when_disconnected(tmp_path: Path) -> None:
    """When JetStream is unavailable, the real ``ArxNatsClient`` WAL-stashes the
    envelope so it replays on the next connect. This proves the publisher
    rides the durable at-least-once path — silent drop is prevented by the
    client's structural WAL, not by the publisher swallowing errors.

    Closes 04b codex MED-2: previous ``publish_fire_and_forget`` path was
    at-most-once and dropped on disconnect (only a structured log)."""

    engine = _StubEngine()
    wal_file = tmp_path / "snapshot-wal.db"
    client = ArxNatsClient(
        nats_url="nats://localhost:4222",
        tenant_id="tenant-a",
        runner_id="runner-1",
        wal_path=wal_file,
    )
    # ``connect()`` is skipped — we simulate the disconnected boot state so
    # the WAL stash path is exercised without touching a real broker.

    publisher = StateSnapshotPublisher(
        engine=engine,
        nats_client=client,
        tenant_id="tenant-a",
        runner_id="runner-1",
        interval_secs=0.01,
    )

    try:
        await publisher.publish_once(spec_id="spec-1")

        # WAL now has exactly one row containing our snapshot subject.
        pending = client._wal.drain()
        assert len(pending) == 1
        _row_id, subject, payload = pending[0]
        assert subject.startswith("arx.tenant-a.snapshot.state.")
        # Payload carries the same Decimal-safe shape (round-trip through the
        # WAL preserves bytes).
        decoded = json.loads(payload)
        assert decoded["payload"]["runner_id"] == "runner-1"
        assert decoded["payload"]["spec_id"] == "spec-1"
    finally:
        client._wal.close()


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
