"""End-to-end telemetry / pre-trade-reject flow.

Wires the real ``TelemetryActor`` + ``NtTelemetryBridge`` + ``NtRiskEngineBridge``
to a dispatching MessageBus and a recording NATS client, then pushes events and
asserts the full data path — MessageBus event → normalize → actor → adapter →
NATS envelope on the right subject. The core flow runs on a base install with
fake events; one variant drives a *real* NT OrderFilled through a real NT
MessageBus to lock the actual 1.230 dispatch contract (lesson #25).

Deploy-level attach wiring is covered in test_nt_trading_node_host.py; here we
exercise the data path the deploy attach builds.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custos.core.nats_client import NatsEnvelope
from custos.core.telemetry_actor import (
    DEFAULT_TELEMETRY_EVENT_TYPES,
    ArxNatsTelemetryAdapter,
    NtTelemetryBridge,
    TelemetryActor,
    TelemetryActorConfig,
)
from custos.engines.nautilus.risk import NtRiskEngineBridge


class _RecordingNatsClient:
    """Fake ArxNatsClient: records envelope publishes (telemetry + reject share
    ``publish_telemetry_envelope``; heartbeat rides ``publish_fire_and_forget``)."""

    def __init__(self, *, tenant_id: str = "acme", runner_id: str = "runner-7", fail: bool = False):
        self.tenant_id = tenant_id
        self.runner_id = runner_id
        self._fail = fail
        self.envelope_calls: list[tuple[str, NatsEnvelope]] = []
        self.fire_and_forget_calls: list[tuple[str, bytes]] = []

    async def publish_telemetry_envelope(self, subject: str, envelope: NatsEnvelope) -> None:
        if self._fail:
            raise RuntimeError("simulated broker outage")
        self.envelope_calls.append((subject, envelope))

    async def publish_fire_and_forget(self, subject: str, payload: bytes) -> None:
        self.fire_and_forget_calls.append((subject, payload))


class _DispatchingMsgBus:
    """MessageBus double: dispatches a publish to every subscription whose
    ``events.x.*`` pattern prefix-matches the topic (NT glob semantics, enough
    for the order/position topics this bridge uses)."""

    def __init__(self) -> None:
        self._subs: list[tuple[str, Any]] = []

    def subscribe(self, topic: str, handler: Any) -> None:
        self._subs.append((topic, handler))

    def publish(self, topic: str, event: Any) -> None:
        for pattern, handler in self._subs:
            prefix = pattern[:-1] if pattern.endswith("*") else pattern
            if topic.startswith(prefix):
                handler(event)


class OrderFilled:  # fake NT event (name matches the class the bridge filters on)
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    @staticmethod
    def to_dict(obj: OrderFilled) -> dict[str, Any]:
        return obj._payload


class OrderDenied:  # fake NT event
    def __init__(self, **attrs: Any) -> None:
        for key, value in attrs.items():
            setattr(self, key, value)


def _fake_fill() -> OrderFilled:
    return OrderFilled(
        {
            "instrument_id": "BTCUSDT.BINANCE",
            "order_side": "BUY",
            "last_qty": "0.5",
            "last_px": "42000.10",
            "client_order_id": "O-1",
            "commission": "0.42000000 USDT",
            "ts_event": 1_700_000_000_000_000_000,
        }
    )


async def _wire(client: _RecordingNatsClient, msgbus: _DispatchingMsgBus) -> TelemetryActor:
    actor = TelemetryActor(
        publisher=ArxNatsTelemetryAdapter(client),  # type: ignore[arg-type]
        tenant_id=client.tenant_id,
        runner_id=client.runner_id,
        config=TelemetryActorConfig(
            allowed_event_types=DEFAULT_TELEMETRY_EVENT_TYPES,
            flush_interval_secs=0.02,
            heartbeat_interval_secs=100.0,  # keep heartbeats out of the short window
        ),
    )
    await actor.start()
    NtTelemetryBridge(actor=actor).bootstrap(msgbus)
    NtRiskEngineBridge(
        client=client,  # type: ignore[arg-type]
        tenant_id=client.tenant_id,
        runner_id=client.runner_id,
    ).bootstrap(msgbus)
    return actor


@pytest.mark.asyncio
async def test_fill_event_flows_to_nats() -> None:
    client = _RecordingNatsClient()
    bus = _DispatchingMsgBus()
    actor = await _wire(client, bus)
    try:
        bus.publish("events.order.ST-1", _fake_fill())
        await asyncio.sleep(0.1)  # let the flush loop publish
    finally:
        await actor.stop()

    assert len(client.envelope_calls) == 1
    subject, envelope = client.envelope_calls[0]
    assert subject == f"arx.acme.telemetry.runner-7.{actor.session_id}"
    assert envelope.payload["event_type"] == "OrderFilled"
    assert envelope.payload["qty"] == "0.5"
    assert envelope.payload["price"] == "42000.10"
    assert envelope.payload["symbol"] == "BTCUSDT.BINANCE"


@pytest.mark.asyncio
async def test_order_denied_flows_to_pre_trade_reject_subject() -> None:
    client = _RecordingNatsClient()
    bus = _DispatchingMsgBus()
    actor = await _wire(client, bus)
    try:
        denied = OrderDenied(reason="notional over limit", instrument_id="BTCUSDT.BINANCE")
        bus.publish("events.order.ST-1", denied)
        await asyncio.sleep(0.1)  # risk bridge schedules the async publish
    finally:
        await actor.stop()

    reject_calls = [c for c in client.envelope_calls if "pre_trade_reject" in c[0]]
    assert len(reject_calls) == 1
    subject, envelope = reject_calls[0]
    assert subject == "arx.acme.pre_trade_reject.runner-7"
    assert envelope.payload["reject_reason"] == "max_notional"
    assert envelope.payload["symbol"] == "BTCUSDT.BINANCE"


@pytest.mark.asyncio
async def test_nats_publish_fail_does_not_crash_actor() -> None:
    # 红线 0.3: a broker outage must not crash the actor or the NT thread — the
    # failure is logged + counted, the flush loop stays alive.
    client = _RecordingNatsClient(fail=True)
    bus = _DispatchingMsgBus()
    actor = await _wire(client, bus)
    try:
        bus.publish("events.order.ST-1", _fake_fill())
        await asyncio.sleep(0.1)
        assert actor._flush_task is not None  # loop survived the publish exception
        assert actor.drop_count() >= 1  # failure counted, not silently swallowed
    finally:
        await actor.stop()


@pytest.mark.asyncio
async def test_multiple_specs_isolated_by_session_id() -> None:
    # Two deployments → two actors with distinct session_ids; an event on one
    # spec's bus never lands on the other's client (no cross-spec event mixing).
    client_a, bus_a = _RecordingNatsClient(), _DispatchingMsgBus()
    client_b, bus_b = _RecordingNatsClient(), _DispatchingMsgBus()
    actor_a = await _wire(client_a, bus_a)
    actor_b = await _wire(client_b, bus_b)
    try:
        assert actor_a.session_id != actor_b.session_id
        bus_a.publish("events.order.ST-1", _fake_fill())
        await asyncio.sleep(0.1)
    finally:
        await actor_a.stop()
        await actor_b.stop()

    assert len(client_a.envelope_calls) == 1
    assert client_b.envelope_calls == []  # spec B saw none of spec A's events
    _, envelope_a = client_a.envelope_calls[0]
    assert envelope_a.ordering.session_id == actor_a.session_id


@pytest.mark.asyncio
async def test_real_nt_fill_flows_end_to_end() -> None:
    # lesson #25: drive a REAL NT OrderFilled through a REAL NT MessageBus so the
    # actual 1.230 dispatch + serialisation contract is exercised end to end.
    pytest.importorskip("nautilus_trader")
    from nautilus_trader.common.component import LiveClock, MessageBus
    from nautilus_trader.core.uuid import UUID4
    from nautilus_trader.model.enums import LiquiditySide, OrderSide, OrderType
    from nautilus_trader.model.events import OrderFilled as NtOrderFilled
    from nautilus_trader.model.identifiers import (
        AccountId,
        ClientOrderId,
        InstrumentId,
        PositionId,
        StrategyId,
        TradeId,
        TraderId,
        VenueOrderId,
    )
    from nautilus_trader.model.objects import Currency, Money, Price, Quantity

    client = _RecordingNatsClient()
    bus = MessageBus(trader_id=TraderId("CUSTOS-1"), clock=LiveClock())
    actor = await _wire(client, bus)
    try:
        fill = NtOrderFilled(
            trader_id=TraderId("CUSTOS-1"),
            strategy_id=StrategyId("ST-1"),
            instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE"),
            client_order_id=ClientOrderId("O-1"),
            venue_order_id=VenueOrderId("V-1"),
            account_id=AccountId("BINANCE-001"),
            trade_id=TradeId("T-1"),
            position_id=PositionId("P-1"),
            order_side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            last_qty=Quantity.from_str("0.5"),
            last_px=Price.from_str("42000.10"),
            currency=Currency.from_str("USDT"),
            commission=Money.from_str("0.42 USDT"),
            liquidity_side=LiquiditySide.TAKER,
            event_id=UUID4(),
            ts_event=1_700_000_000_000_000_000,
            ts_init=1_700_000_000_000_000_000,
        )
        bus.publish("events.order.ST-1", fill)
        await asyncio.sleep(0.1)
    finally:
        await actor.stop()

    assert len(client.envelope_calls) == 1
    _, envelope = client.envelope_calls[0]
    assert envelope.payload["event_type"] == "OrderFilled"
    assert envelope.payload["qty"] == "0.5"
    assert envelope.payload["price"] == "42000.10"
