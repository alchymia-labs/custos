"""NT RiskEngine bootstrap + OrderDenied → NATS bridge.

Covers the failure-mode contract for the runner edge:

* 4 reject reasons → published ``PreTradeRejected`` envelope on the canonical
  subject (cross-language wire round-trip — payload matches the Rust struct).
* NT MessageBus down → bootstrap fail-fast (no silent no-op).
* reference_price missing → degraded warning logged, event still published.
* warm-start consistency → identical config across a restart.

NautilusTrader is not installed in the runner; the bridge is ducktyped over
the MessageBus so these run without the engine. JetStream is mocked.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog

from arx_runner.nats_client import ArxNatsClient
from arx_runner.nt_risk_engine import (
    PRE_TRADE_REJECTED_FIELDS,
    NtRiskEngineBridge,
    PreTradeRuleConfig,
    _denied_ts_seconds,
    bootstrap_from_rules,
    build_nt_risk_engine_config,
    order_fingerprint,
)


@dataclass
class FakeOrderDenied:
    reason: str
    instrument_id: str
    rule_id: str
    side: str = "Buy"
    quantity: str = "11"
    price: str = "100"
    ts_seconds: int = 1_700_000_000
    reference_price: str | None = "100"


def _client() -> tuple[ArxNatsClient, MagicMock]:
    client = ArxNatsClient(
        nats_url="nats://localhost:4222",
        tenant_id="acme",
        runner_id="runner-7",
    )
    fake_js = MagicMock()
    fake_js.publish = AsyncMock()
    client._js = fake_js  # bypass real connect
    return client, fake_js


def _rules() -> list[PreTradeRuleConfig]:
    return [
        PreTradeRuleConfig(
            rule_id="rule-a",
            strategy_id=None,
            symbol="BTCUSDT",
            max_qty=Decimal("10"),
            max_notional=Decimal("100000"),
            notional_ccy="USDT",
            price_collar_bps=200,
            dedup_window_ms=1000,
        ),
        PreTradeRuleConfig(
            rule_id="rule-b",
            strategy_id=None,
            symbol=None,
            max_qty=Decimal("5"),
            max_notional=Decimal("50000"),
            notional_ccy="USDT",
            price_collar_bps=0,
            dedup_window_ms=0,
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("nt_reason", "expected"),
    [
        ("MAX_QUANTITY exceeded", "max_qty"),
        ("notional over limit", "max_notional"),
        ("price collar breach", "price_collar"),
        ("duplicate order", "duplicate"),
    ],
)
async def test_order_denied_publishes_pre_trade_rejected(nt_reason, expected) -> None:
    client, fake_js = _client()
    bridge = NtRiskEngineBridge(client=client, tenant_id="acme", runner_id="runner-7")

    denied = FakeOrderDenied(reason=nt_reason, instrument_id="BTCUSDT", rule_id="rule-a")
    await bridge.on_order_denied(denied)

    fake_js.publish.assert_awaited_once()
    args, kwargs = fake_js.publish.call_args
    subject = args[0] if args else kwargs["subject"]
    payload_bytes = args[1] if len(args) > 1 else kwargs["payload"]

    assert subject == "arx.acme.pre_trade_reject.runner-7"
    decoded = json.loads(payload_bytes)
    # Envelope shape
    assert decoded["tenant_id"] == "acme"
    # Cross-language wire contract: payload carries exactly the Rust fields.
    assert set(decoded["payload"].keys()) == set(PRE_TRADE_REJECTED_FIELDS)
    assert decoded["payload"]["reject_reason"] == expected
    assert decoded["payload"]["symbol"] == "BTCUSDT"
    assert decoded["payload"]["rule_id"] == "rule-a"
    # fingerprint is a 64-char sha256 hex digest
    assert len(decoded["payload"]["order_fingerprint"]) == 64


def test_bootstrap_fails_fast_when_message_bus_down() -> None:
    client, _ = _client()
    bridge = NtRiskEngineBridge(client=client, tenant_id="acme", runner_id="runner-7")
    with pytest.raises(RuntimeError, match="MessageBus unavailable"):
        bridge.bootstrap(None)


@pytest.mark.asyncio
async def test_bootstrap_from_rules_fails_fast_when_bus_none() -> None:
    client, _ = _client()
    with pytest.raises(RuntimeError, match="MessageBus unavailable"):
        await bootstrap_from_rules(
            client=client,
            rules=_rules(),
            message_bus=None,
            tenant_id="acme",
            runner_id="runner-7",
        )


@pytest.mark.asyncio
async def test_bootstrap_subscribes_order_wildcard_topic() -> None:
    # NT publishes order events on events.order.{strategy_id}; a literal
    # events.order.OrderDenied topic never matches (dead subscription). The
    # bridge must subscribe with the wildcard tail (DEV-00B-DEAD-SUBSCRIPTION).
    client, _ = _client()
    bus = MagicMock()
    bridge = await bootstrap_from_rules(
        client=client,
        rules=_rules(),
        message_bus=bus,
        tenant_id="acme",
        runner_id="runner-7",
    )
    bus.subscribe.assert_called_once()
    topic = bus.subscribe.call_args.args[0]
    assert topic == "events.order.*"
    assert bridge.subject() == "arx.acme.pre_trade_reject.runner-7"


@pytest.mark.asyncio
async def test_dispatcher_ignores_non_denied_order_events() -> None:
    # The order-event stream carries submits / accepts / fills too; only
    # OrderDenied is republished. The type filter is a live guard — a fill
    # must never publish a pre-trade reject.
    client, fake_js = _client()
    bus = MagicMock()
    bridge = NtRiskEngineBridge(client=client, tenant_id="acme", runner_id="runner-7")
    bridge.bootstrap(bus)

    class OrderAccepted:  # order event that is not a denial
        pass

    bridge._on_order_event(OrderAccepted())
    await asyncio.sleep(0.01)
    fake_js.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatcher_forwards_real_order_denied() -> None:
    # lesson #25: prove the bridge fires against a REAL NT OrderDenied (the
    # actual 1.230 event), not just the hand-written fake. The sync MessageBus
    # callback schedules the async publish on the captured runner loop.
    pytest.importorskip("nautilus_trader")
    from nautilus_trader.core.uuid import UUID4
    from nautilus_trader.model.events import OrderDenied
    from nautilus_trader.model.identifiers import (
        ClientOrderId,
        InstrumentId,
        StrategyId,
        TraderId,
    )

    client, fake_js = _client()
    bus = MagicMock()
    bridge = NtRiskEngineBridge(client=client, tenant_id="acme", runner_id="runner-7")
    bridge.bootstrap(bus)

    denied = OrderDenied(
        trader_id=TraderId("CUSTOS-1"),
        strategy_id=StrategyId("ST-1"),
        instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE"),
        client_order_id=ClientOrderId("O-1"),
        reason="MAX_NOTIONAL exceeded",
        event_id=UUID4(),
        ts_init=1_700_000_000_000_000_000,
    )
    bridge._on_order_event(denied)
    await asyncio.sleep(0.05)  # let the scheduled publish task run

    fake_js.publish.assert_awaited_once()
    args, kwargs = fake_js.publish.call_args
    subject = args[0] if args else kwargs["subject"]
    payload_bytes = args[1] if len(args) > 1 else kwargs["payload"]
    assert subject == "arx.acme.pre_trade_reject.runner-7"
    decoded = json.loads(payload_bytes)
    assert decoded["payload"]["symbol"] == "BTCUSDT.BINANCE"
    assert decoded["payload"]["reject_reason"] == "max_notional"
    assert set(decoded["payload"].keys()) == set(PRE_TRADE_REJECTED_FIELDS)
    # The correlation handle folds in client_order_id — the stable field a real
    # OrderDenied carries (side / quantity / price are absent on the NT event).
    # Recomputing with the same id matches; a different id diverges, proving the
    # dispatch path fed "O-1" into the fingerprint.
    ts = _denied_ts_seconds(denied)
    assert decoded["payload"]["order_fingerprint"] == order_fingerprint(
        "BTCUSDT.BINANCE", "O-1", "", "", "", ts
    )
    assert decoded["payload"]["order_fingerprint"] != order_fingerprint(
        "BTCUSDT.BINANCE", "O-2", "", "", "", ts
    )


@pytest.mark.asyncio
async def test_denied_shape_mismatch() -> None:
    # An OrderDenied-typed event missing the defining fields (NT version drift)
    # is skipped with a structured log, never publishing a garbage rejection.
    client, fake_js = _client()
    bridge = NtRiskEngineBridge(client=client, tenant_id="acme", runner_id="runner-7")

    class OrderDenied:  # right type name, wrong shape (no reason / instrument_id)
        pass

    with structlog.testing.capture_logs() as logs:
        await bridge.on_order_denied(OrderDenied())

    assert "pre_trade_reject_event_shape_mismatch" in [e.get("event") for e in logs]
    fake_js.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_reference_price_missing_logs_degraded_and_still_publishes() -> None:
    client, fake_js = _client()
    bridge = NtRiskEngineBridge(client=client, tenant_id="acme", runner_id="runner-7")

    denied = FakeOrderDenied(
        reason="price collar breach",
        instrument_id="BTCUSDT",
        rule_id="rule-a",
        reference_price=None,  # quote unavailable → degraded collar
    )
    with structlog.testing.capture_logs() as logs:
        await bridge.on_order_denied(denied)

    events = [log["event"] for log in logs]
    assert "pre_trade_reference_price_missing" in events
    # The event is still published — degradation never drops the rejection.
    fake_js.publish.assert_awaited_once()


def test_warm_start_config_is_deterministic() -> None:
    # A runner restart reloads the same rules → byte-identical NT config.
    first = build_nt_risk_engine_config(_rules())
    # Reverse order to prove sort-stability (order-independent).
    second = build_nt_risk_engine_config(list(reversed(_rules())))
    assert first == second
    assert first["max_notionals_per_order"] == {"BTCUSDT": "100000", "*": "50000"}
    assert first["bypass"] is False


def test_fingerprint_is_stable_and_hex() -> None:
    a = order_fingerprint("BTCUSDT", "O-1", "Buy", "11", "100", 1_700_000_000)
    b = order_fingerprint("BTCUSDT", "O-1", "Buy", "11", "100", 1_700_000_000)
    c = order_fingerprint("BTCUSDT", "O-1", "Sell", "11", "100", 1_700_000_000)
    d = order_fingerprint("BTCUSDT", "O-2", "Buy", "11", "100", 1_700_000_000)
    assert a == b
    assert a != c
    # client_order_id participates in the correlation handle (uniqueness lift).
    assert a != d
    assert len(a) == 64


def test_rule_config_from_dict_uses_decimal_not_float() -> None:
    rule = PreTradeRuleConfig.from_dict(
        {
            "rule_id": "r1",
            "symbol": "BTCUSDT",
            "max_qty": "10.5",
            "max_notional": "100000.25",
            "notional_ccy": "USDT",
            "price_collar_bps": 200,
            "dedup_window_ms": 1000,
        }
    )
    assert isinstance(rule.max_qty, Decimal)
    assert rule.max_qty == Decimal("10.5")
    assert rule.max_notional == Decimal("100000.25")
