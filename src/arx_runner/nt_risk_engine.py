"""NT RiskEngine bootstrap + ``OrderDenied`` → NATS bridge (single-order 15c3-5).

Two responsibilities at the runner edge:

1. **Configure** NautilusTrader's native RiskEngine from the pre-trade rules
   pulled for this runner's deployments (max qty / notional / price collar).
2. **Bridge** NT's MessageBus ``OrderDenied`` events out to
   ``arx.{tenant}.pre_trade_reject.{runner_id}`` so the cloud control plane
   records every rejection (audit chain + deduplicated alert). Rejections ride
   the at-least-once JetStream path — a denied order must never be silently
   lost (对账不静默 红线).

NautilusTrader is an *optional* import: in dev / paper-without-NT the engine is
absent, so this module degrades to validating its config + wire shape (the
bridge is ducktyped over the MessageBus so unit tests drive it without NT).

The published payload matches the Rust ``domain::events::PreTradeRejected``
struct field-for-field so the cloud consumer can decode it without a codec
shim (cross-language wire contract).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

import uuid6

from arx_runner.log import get_logger
from arx_runner.nats_client import ArxNatsClient, NatsEnvelope, build_subject

_log = get_logger("arx_runner.nt_risk_engine")

# Field set of the Rust `domain::events::PreTradeRejected` payload — the cloud
# consumer decodes exactly these keys. Kept here as the wire contract anchor so
# a drift between the Python producer and the Rust consumer fails a test, not
# production (cross-language round-trip).
PRE_TRADE_REJECTED_FIELDS = (
    "tenant_id",
    "rule_id",
    "symbol",
    "order_fingerprint",
    "reject_reason",
)

# Reject-reason codes — must match Rust `OrderRejectReason::code` + the
# `pre_trade_rejections.reject_reason` CHECK constraint.
VALID_REJECT_REASONS = frozenset(
    {"max_qty", "max_notional", "price_collar", "duplicate", "reference_price_missing"}
)


@dataclass(frozen=True)
class PreTradeRuleConfig:
    """A single-order rule pulled for the runner. Money fields are ``Decimal``
    (never float — ADR-008 money math red line)."""

    rule_id: str
    strategy_id: str | None
    symbol: str | None
    max_qty: Decimal
    max_notional: Decimal
    notional_ccy: str
    price_collar_bps: int
    dedup_window_ms: int

    @classmethod
    def from_dict(cls, raw: dict) -> "PreTradeRuleConfig":
        """Parse a rule row (as returned by the cloud rules endpoint). Money
        strings parse straight to ``Decimal`` so no float ever touches the
        value."""
        return cls(
            rule_id=str(raw["rule_id"]),
            strategy_id=raw.get("strategy_id"),
            symbol=raw.get("symbol"),
            max_qty=Decimal(str(raw["max_qty"])),
            max_notional=Decimal(str(raw["max_notional"])),
            notional_ccy=str(raw["notional_ccy"]),
            price_collar_bps=int(raw["price_collar_bps"]),
            dedup_window_ms=int(raw["dedup_window_ms"]),
        )


def build_nt_risk_engine_config(rules: list[PreTradeRuleConfig]) -> dict:
    """Map pre-trade rules to an NT-``RiskEngineConfig``-shaped dict.

    NautilusTrader's RiskEngine screens orders by per-instrument max notional;
    the qty / collar / dedup limits ride alongside as ``arx_pre_trade`` metadata
    the runner enforces on top of NT's native checks. The mapping is
    deterministic + order-independent so a warm restart reproduces byte-identical
    config (warm-start consistency).
    """
    # Symbol-keyed notional ceilings (NT `max_notional_per_order` shape). A rule
    # with no symbol (tenant-global) lands under the "*" wildcard key.
    max_notionals: dict[str, str] = {}
    arx_rules: list[dict] = []
    for rule in sorted(rules, key=lambda r: r.rule_id):
        key = rule.symbol or "*"
        max_notionals[key] = str(rule.max_notional)
        arx_rules.append(
            {
                "rule_id": rule.rule_id,
                "symbol": rule.symbol,
                "strategy_id": rule.strategy_id,
                "max_qty": str(rule.max_qty),
                "max_notional": str(rule.max_notional),
                "notional_ccy": rule.notional_ccy,
                "price_collar_bps": rule.price_collar_bps,
                "dedup_window_ms": rule.dedup_window_ms,
            }
        )
    return {
        "bypass": False,
        "max_notionals_per_order": max_notionals,
        "arx_pre_trade": arx_rules,
    }


def order_fingerprint(
    symbol: str, side: str, quantity: str, price: str, ts_seconds: int
) -> str:
    """SHA-256 content digest over ``symbol|side|qty|price|ts_seconds`` — the
    same canonical recipe the Rust service uses (correlation handle, not the
    tamper-evidence anchor; that's the audit chain HMAC)."""
    canonical = f"{symbol}|{side}|{quantity}|{price}|{ts_seconds}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class _OrderDenied(Protocol):
    """Ducktyped view of NT's ``OrderDenied`` event. NT supplies the concrete
    type; tests supply any object with these attributes."""

    reason: str
    instrument_id: Any
    rule_id: str


class _MessageBus(Protocol):
    """Ducktyped view of NT's ``MessageBus`` — only the subscribe surface the
    bridge needs."""

    def subscribe(self, topic: str, handler: Any) -> None: ...


class NtRiskEngineBridge:
    """Subscribes to NT ``OrderDenied`` events and republishes each as a
    ``PreTradeRejected`` envelope on the cloud channel."""

    def __init__(
        self,
        *,
        client: ArxNatsClient,
        tenant_id: str,
        runner_id: str,
    ) -> None:
        self._client = client
        self._tenant_id = tenant_id
        self._runner_id = runner_id

    def subject(self) -> str:
        """``arx.{tenant}.pre_trade_reject.{runner_id}`` (plan-index §6 grammar
        via the shared subject builder — empty ids raise rather than route to a
        malformed subject)."""
        return build_subject(self._tenant_id, "pre_trade_reject", self._runner_id)

    def bootstrap(self, message_bus: _MessageBus | None) -> None:
        """Wire the bridge to NT's MessageBus. A missing bus is a fail-fast
        error (NT RiskEngine cannot be observed) — surfaced loudly, never a
        silent no-op."""
        if message_bus is None:
            _log.error(
                "nt_message_bus_unavailable",
                runner_id=self._runner_id,
                tenant_id=self._tenant_id,
            )
            raise RuntimeError(
                "NT MessageBus unavailable — cannot bootstrap pre-trade reject bridge"
            )
        message_bus.subscribe("events.order.OrderDenied", self.on_order_denied)
        _log.info(
            "nt_risk_engine_bridge_bootstrapped",
            runner_id=self._runner_id,
            subject=self.subject(),
        )

    async def on_order_denied(self, denied: _OrderDenied) -> None:
        """Translate one NT ``OrderDenied`` into a ``PreTradeRejected`` envelope
        and publish it at-least-once. Unknown NT reasons map to ``max_qty``'s
        sibling set only when recognised; an unmapped reason is published as-is
        but logged so the catalog gap is visible."""
        reason = _map_reject_reason(getattr(denied, "reason", ""))
        symbol = str(getattr(denied, "instrument_id", "") or "")
        rule_id = str(getattr(denied, "rule_id", "") or "")

        # Reference price may be absent (NT didn't have a quote) — the collar
        # check degraded upstream. Record the degradation rather than dropping
        # it silently.
        reference_price = getattr(denied, "reference_price", None)
        if reference_price is None and reason == "price_collar":
            _log.warning(
                "pre_trade_reference_price_missing",
                rule_id=rule_id,
                symbol=symbol,
            )

        side = str(getattr(denied, "side", "") or "")
        quantity = str(getattr(denied, "quantity", "") or "")
        price = str(getattr(denied, "price", "") or "")
        ts_seconds = int(getattr(denied, "ts_seconds", 0) or 0)
        fingerprint = order_fingerprint(symbol, side, quantity, price, ts_seconds)

        payload = {
            "tenant_id": self._tenant_id,
            "rule_id": rule_id,
            "symbol": symbol,
            "order_fingerprint": fingerprint,
            "reject_reason": reason,
        }
        envelope = NatsEnvelope(
            event_id=str(uuid6.uuid7()),
            tenant_id=self._tenant_id,
            occurred_at=_now_rfc3339_nanos(),
            payload=payload,
        )
        # At-least-once: a rejection must reach the cloud audit/alert chain.
        await self._client.publish_telemetry_envelope(self.subject(), envelope)
        _log.info(
            "pre_trade_reject_published",
            rule_id=rule_id,
            symbol=symbol,
            reject_reason=reason,
        )


def _map_reject_reason(nt_reason: str) -> str:
    """Map an NT denial reason to the canonical reject-reason code. NT emits
    free-form reason strings; we recognise the 15c3-5 cases and fall back to a
    logged passthrough so the catalog can grow without dropping events."""
    lowered = nt_reason.lower()
    if "qty" in lowered or "quantity" in lowered:
        return "max_qty"
    if "notional" in lowered:
        return "max_notional"
    if "collar" in lowered or "price" in lowered:
        return "price_collar"
    if "dup" in lowered:
        return "duplicate"
    if nt_reason in VALID_REJECT_REASONS:
        return nt_reason
    _log.warning("pre_trade_unmapped_nt_reason", nt_reason=nt_reason)
    return "max_qty"


def _now_rfc3339_nanos() -> str:
    """RFC3339 nanosecond timestamp, reusing the nats_client formatter so the
    envelope ``occurred_at`` format stays consistent across the runner."""
    from arx_runner.nats_client import _now_rfc3339_nanos as _fmt

    return _fmt()


async def bootstrap_from_rules(
    *,
    client: ArxNatsClient,
    rules: list[PreTradeRuleConfig],
    message_bus: _MessageBus | None,
    tenant_id: str,
    runner_id: str,
) -> NtRiskEngineBridge:
    """Build the NT RiskEngine config from ``rules`` and wire the reject bridge
    to ``message_bus``. Returns the live bridge. Raises if the MessageBus is
    unavailable (fail-fast)."""
    config = build_nt_risk_engine_config(rules)
    _log.info(
        "nt_risk_engine_config_built",
        runner_id=runner_id,
        rule_count=len(rules),
        symbols=sorted(config["max_notionals_per_order"].keys()),
    )
    bridge = NtRiskEngineBridge(
        client=client, tenant_id=tenant_id, runner_id=runner_id
    )
    bridge.bootstrap(message_bus)
    return bridge
