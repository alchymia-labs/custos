"""NT MessageBus → TelemetryActor bridge + payload normalizers.

The bridge subscribes to the NautilusTrader MessageBus order / position event
topics and forwards a money-safe summary of each whitelisted event into the
``TelemetryActor.on_event`` fast path. Normalizers turn a real NT event into a
wire-safe ``dict`` (every money field arrives as ``str``, never ``float`` —
ADR-008 / non-custodial 红线 0.4).

The normalizer tests build *real* NT events (skipped on a base install without
the nautilus extra) so they lock the actual NT 1.230 wire contract, not a
hand-written mirror. The bridge dispatch tests use fake events + a fake
MessageBus so the subscribe / filter / shape-mismatch / fail-safe logic runs on
a base install without NT.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
import structlog

from custos.core.telemetry_actor import (
    DEFAULT_TELEMETRY_EVENT_TYPES,
    MONEY_FIELD_NAMES,
    NtTelemetryBridge,
    normalize_fill_event,
    normalize_position_event,
)

# ----------------------------------------------------------------------
# Real NT event builders (nautilus only). Skipped on a base install.
# ----------------------------------------------------------------------


def _real_order_filled(*, side: str = "BUY", qty: str = "0.5", px: str = "42000.10"):
    from nautilus_trader.core.uuid import UUID4
    from nautilus_trader.model.enums import LiquiditySide, OrderSide, OrderType
    from nautilus_trader.model.events import OrderFilled
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

    return OrderFilled(
        trader_id=TraderId("CUSTOS-1"),
        strategy_id=StrategyId("ST-1"),
        instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE"),
        client_order_id=ClientOrderId("O-1"),
        venue_order_id=VenueOrderId("V-1"),
        account_id=AccountId("BINANCE-001"),
        trade_id=TradeId("T-1"),
        position_id=PositionId("P-1"),
        order_side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
        order_type=OrderType.MARKET,
        last_qty=Quantity.from_str(qty),
        last_px=Price.from_str(px),
        currency=Currency.from_str("USDT"),
        commission=Money.from_str("0.42 USDT"),
        liquidity_side=LiquiditySide.TAKER,
        event_id=UUID4(),
        ts_event=1_700_000_000_000_000_000,
        ts_init=1_700_000_000_000_000_000,
    )


def _real_position_opened(*, pnl: str = "1.50 USDT"):
    from nautilus_trader.core.uuid import UUID4
    from nautilus_trader.model.events import PositionOpened

    return PositionOpened.from_dict(
        {
            "trader_id": "CUSTOS-1",
            "strategy_id": "ST-1",
            "instrument_id": "BTCUSDT.BINANCE",
            "position_id": "P-1",
            "account_id": "BINANCE-001",
            "opening_order_id": "O-1",
            "entry": "BUY",
            "side": "LONG",
            "signed_qty": 0.5,
            "quantity": "0.5",
            "peak_qty": "0.5",
            "last_qty": "0.5",
            "last_px": "42000.10",
            "currency": "USDT",
            "avg_px_open": 42000.10,
            "realized_pnl": pnl,
            "duration_ns": 0,
            "event_id": str(UUID4()),
            "ts_event": 1_700_000_000_000_000_000,
            "ts_init": 1_700_000_000_000_000_000,
        }
    )


def _assert_money_fields_are_str(payload: dict[str, Any]) -> None:
    """Every money-typed field in the payload must be ``str`` (never
    ``float``) — the wire money contract (红线 0.4)."""
    for key, value in payload.items():
        if key in MONEY_FIELD_NAMES:
            assert isinstance(value, str), f"money field {key!r} must be str, got {type(value)}"


# ----------------------------------------------------------------------
# Fake event + MessageBus doubles for the bridge dispatch tests.
# `type(event).to_dict(event)` mirrors NT's static-method serialisation.
# ----------------------------------------------------------------------


class OrderFilled:  # test double: name matches the NT event class the bridge filters on
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    @staticmethod
    def to_dict(obj: OrderFilled) -> dict[str, Any]:
        return obj._payload


class PositionChanged:  # test double
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    @staticmethod
    def to_dict(obj: PositionChanged) -> dict[str, Any]:
        return obj._payload


class OrderAccepted:  # test double: an order event NOT on the telemetry whitelist
    @staticmethod
    def to_dict(obj: OrderAccepted) -> dict[str, Any]:
        raise AssertionError("normalizer must never run on a non-whitelisted event")


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


def _fake_position() -> PositionChanged:
    return PositionChanged(
        {
            "instrument_id": "BTCUSDT.BINANCE",
            "side": "LONG",
            "quantity": "0.5",
            "realized_pnl": "1.50000000 USDT",
            "ts_event": 1_700_000_000_000_000_000,
        }
    )


class _FakeMessageBus:
    """Records subscriptions and dispatches by exact topic prefix match with a
    trailing ``*`` wildcard, matching NT's glob-topic semantics closely enough
    for dispatch tests."""

    def __init__(self) -> None:
        self.subscriptions: dict[str, Any] = {}

    def subscribe(self, topic: str, handler: Any) -> None:
        self.subscriptions[topic] = handler

    def publish(self, topic: str, event: Any) -> None:
        for pattern, handler in self.subscriptions.items():
            prefix = pattern[:-1] if pattern.endswith("*") else pattern
            if topic.startswith(prefix):
                handler(event)


class _RecordingActor:
    """Ducktyped TelemetryActor stand-in: records on_event calls."""

    def __init__(self) -> None:
        self.runner_id = "runner-001"
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def on_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.calls.append((event_type, payload))


# ---------------------------------------------------------------------- Task 1


def test_normalize_fill_event_produces_money_safe_summary() -> None:
    pytest.importorskip("nautilus_trader")
    payload = normalize_fill_event(_real_order_filled())
    assert payload["symbol"] == "BTCUSDT.BINANCE"
    assert payload["side"] == "BUY"  # NT enum via order_side_to_str, not str(enum)=='1'
    assert payload["qty"] == "0.5"
    assert payload["price"] == "42000.10"
    assert payload["client_order_id"] == "O-1"
    assert payload["ts_event"] == 1_700_000_000_000_000_000
    # commission Money "0.42 USDT" split into pure-decimal value + currency.
    # NT pads to the currency scale; assert the value + suffix-free contract,
    # not the exact scale (consumer quantizes — common-errors.md money tail).
    assert " " not in payload["fee"]
    assert Decimal(payload["fee"]) == Decimal("0.42")
    assert payload["fee_ccy"] == "USDT"
    _assert_money_fields_are_str(payload)


def test_normalize_position_event_splits_money_and_currency() -> None:
    pytest.importorskip("nautilus_trader")
    payload = normalize_position_event(_real_position_opened(pnl="1.50 USDT"))
    assert payload["symbol"] == "BTCUSDT.BINANCE"
    assert payload["side"] == "LONG"  # position_side_to_str
    assert payload["qty"] == "0.5"
    # realized_pnl Money "1.50 USDT" → pure-decimal value + currency (no suffix on wire)
    assert " " not in payload["pnl"], "wire money must be pure str(Decimal), no currency suffix"
    assert Decimal(payload["pnl"]) == Decimal("1.50")
    assert payload["pnl_ccy"] == "USDT"
    _assert_money_fields_are_str(payload)


def test_default_event_type_whitelist_covers_fill_and_positions() -> None:
    # The whitelist is the schema allowlist the actor filters on; drifting NT
    # event names must not silently leak (or silently stop being forwarded).
    assert "OrderFilled" in DEFAULT_TELEMETRY_EVENT_TYPES
    assert {"PositionOpened", "PositionChanged", "PositionClosed"} <= DEFAULT_TELEMETRY_EVENT_TYPES
    # OrderDenied is NOT telemetry — it rides the pre_trade_reject subject.
    assert "OrderDenied" not in DEFAULT_TELEMETRY_EVENT_TYPES


# ---------------------------------------------------------------------- Task 2


def test_bridge_bootstrap_subscribes_order_and_position_topics() -> None:
    bus = _FakeMessageBus()
    bridge = NtTelemetryBridge(actor=_RecordingActor())
    bridge.bootstrap(bus)
    # NT publishes order events on events.order.{strategy_id} and positions on
    # events.position.{strategy_id}; a literal type-named topic never matches,
    # so the bridge must subscribe with the wildcard tail (DEV-00B-DEAD-SUBSCRIPTION).
    assert set(bus.subscriptions) == {"events.order.*", "events.position.*"}


def test_bridge_forwards_fill_to_actor() -> None:
    bus = _FakeMessageBus()
    actor = _RecordingActor()
    NtTelemetryBridge(actor=actor).bootstrap(bus)
    bus.publish("events.order.ST-1", _fake_fill())
    assert len(actor.calls) == 1
    event_type, payload = actor.calls[0]
    assert event_type == "OrderFilled"
    assert payload["qty"] == "0.5"
    assert payload["price"] == "42000.10"
    assert payload["symbol"] == "BTCUSDT.BINANCE"


def test_bridge_forwards_position_to_actor() -> None:
    bus = _FakeMessageBus()
    actor = _RecordingActor()
    NtTelemetryBridge(actor=actor).bootstrap(bus)
    bus.publish("events.position.ST-1", _fake_position())
    assert len(actor.calls) == 1
    event_type, payload = actor.calls[0]
    assert event_type == "PositionChanged"
    assert payload["qty"] == "0.5"
    assert Decimal(payload["pnl"]) == Decimal("1.50")


def test_bridge_ignores_non_whitelisted_order_events() -> None:
    # An order event that is not a fill (accepted / submitted / denied) must not
    # be forwarded to the telemetry channel — the type filter is a live guard.
    bus = _FakeMessageBus()
    actor = _RecordingActor()
    NtTelemetryBridge(actor=actor).bootstrap(bus)
    bus.publish("events.order.ST-1", OrderAccepted())
    assert actor.calls == []


def test_shape_mismatch_skipped() -> None:
    # An OrderFilled whose serialisation is missing a required key (NT version
    # drift) is skipped with a structured log — never crashes the NT thread.
    bus = _FakeMessageBus()
    actor = _RecordingActor()
    NtTelemetryBridge(actor=actor).bootstrap(bus)
    broken = OrderFilled({"instrument_id": "BTCUSDT.BINANCE"})  # missing last_qty etc.
    with structlog.testing.capture_logs() as logs:
        bus.publish("events.order.ST-1", broken)
    assert actor.calls == []
    assert "telemetry_event_shape_mismatch" in [e.get("event") for e in logs]


def test_bridge_forward_never_crashes_on_actor_error() -> None:
    # 红线 0.3: a telemetry failure must never propagate into the NT engine
    # thread. An actor that raises is logged, not re-raised.
    class _ExplodingActor(_RecordingActor):
        def on_event(self, event_type: str, payload: dict[str, Any]) -> None:
            raise RuntimeError("actor boom")

    bus = _FakeMessageBus()
    NtTelemetryBridge(actor=_ExplodingActor()).bootstrap(bus)
    with structlog.testing.capture_logs() as logs:
        bus.publish("events.order.ST-1", _fake_fill())  # must not raise
    assert "telemetry_forward_failed" in [e.get("event") for e in logs]


def test_nt_messagebus_disconnected_logs_and_degrades() -> None:
    # NT MessageBus 断连 / unavailable at bootstrap → fail-fast with a loud log
    # (the deploy-level attach catch degrades it to observability loss, 红线 0.3).
    bridge = NtTelemetryBridge(actor=_RecordingActor())
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(RuntimeError, match="MessageBus unavailable"):
            bridge.bootstrap(None)
    assert "nt_messagebus_disconnected" in [e.get("event") for e in logs]
