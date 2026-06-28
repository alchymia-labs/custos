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
async def test_bootstrap_subscribes_when_bus_present() -> None:
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
    assert bridge.subject() == "arx.acme.pre_trade_reject.runner-7"


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
    a = order_fingerprint("BTCUSDT", "Buy", "11", "100", 1_700_000_000)
    b = order_fingerprint("BTCUSDT", "Buy", "11", "100", 1_700_000_000)
    c = order_fingerprint("BTCUSDT", "Sell", "11", "100", 1_700_000_000)
    assert a == b
    assert a != c
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
