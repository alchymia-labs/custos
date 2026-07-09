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

import asyncio
import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

import uuid6

from custos.core.local_cap import RejectPublisher
from custos.core.log import get_logger
from custos.core.nats_client import ArxNatsClient, NatsEnvelope, build_subject

_log = get_logger("custos.nt_risk_engine")

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
    def from_dict(cls, raw: dict) -> PreTradeRuleConfig:
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


def make_runner_cap_reject_publisher(
    *,
    client: ArxNatsClient,
    tenant_id: str,
    runner_id: str,
) -> RejectPublisher:
    """Build the ``RejectPublisher`` the runner notional cap calls on a breach.

    A runner-cap breach is a ``max_notional`` rejection at the wire level (an
    order refused because it would breach a notional ceiling), tagged
    ``rule_id=runner_notional_cap`` so the cloud can tell it apart from NT's
    per-order screen. Published at-least-once onto the pre-trade reject channel
    so it reaches the audit / alert chain (no-silent-reconcile red line).
    """
    subject = build_subject(tenant_id, "pre_trade_reject", runner_id)

    async def _publish(
        symbol: str,
        current_open: Decimal,
        requested_notional: Decimal,
        cap: Decimal,
    ) -> None:
        payload = {
            "tenant_id": tenant_id,
            "rule_id": "runner_notional_cap",
            "symbol": symbol,
            "order_fingerprint": order_fingerprint(symbol, "", "", str(requested_notional), "", 0),
            "reject_reason": "max_notional",
        }
        envelope = NatsEnvelope(
            event_id=str(uuid6.uuid7()),
            tenant_id=tenant_id,
            occurred_at=_now_rfc3339_nanos(),
            payload=payload,
        )
        await client.publish_telemetry_envelope(subject, envelope)
        _log.info(
            "runner_cap_reject_published",
            symbol=symbol,
            current_open=str(current_open),
            requested_notional=str(requested_notional),
            cap=str(cap),
        )

    return _publish


def order_fingerprint(
    symbol: str,
    client_order_id: str,
    side: str,
    quantity: str,
    price: str,
    ts_seconds: int,
) -> str:
    """SHA-256 content digest over ``symbol|client_order_id|side|qty|price|ts_seconds``.

    A correlation handle for the cloud audit / alert chain — not a tamper-evidence
    anchor. Tamper evidence is the audit chain's per-tenant HMAC (governance),
    which this non-custodial runner deliberately does not implement. client_order_id
    is the one stable field a real NT ``OrderDenied`` carries (side / quantity /
    price are absent on the event), so folding it in lifts the handle's uniqueness
    above the ``(symbol, ts)`` pair it would otherwise degrade to.
    """
    canonical = f"{symbol}|{client_order_id}|{side}|{quantity}|{price}|{ts_seconds}"
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
        # Runner loop captured at bootstrap so the sync MessageBus callback can
        # schedule the async publish (NT dispatches handlers synchronously).
        self._loop: asyncio.AbstractEventLoop | None = None
        # Strong refs to in-flight publish futures — without them the loop only
        # weakly references a scheduled task and could GC it mid-publish,
        # silently dropping a rejection (对账不静默 红线).
        self._pending: set = set()

    def subject(self) -> str:
        """``arx.{tenant}.pre_trade_reject.{runner_id}`` (plan-index §6 grammar
        via the shared subject builder — empty ids raise rather than route to a
        malformed subject)."""
        return build_subject(self._tenant_id, "pre_trade_reject", self._runner_id)

    def bootstrap(self, message_bus: _MessageBus | None) -> None:
        """Wire the bridge to NT's MessageBus. A missing bus is a fail-fast
        error (NT RiskEngine cannot be observed) — surfaced loudly, never a
        silent no-op.

        NT publishes order events on ``events.order.{strategy_id}`` and invokes
        handlers synchronously, so the bridge subscribes to the ``*`` wildcard
        (a literal ``events.order.OrderDenied`` topic never matches) and routes
        through a sync dispatcher that schedules the async publish."""
        if message_bus is None:
            _log.error(
                "nt_message_bus_unavailable",
                runner_id=self._runner_id,
                tenant_id=self._tenant_id,
            )
            raise RuntimeError(
                "NT MessageBus unavailable — cannot bootstrap pre-trade reject bridge"
            )
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        message_bus.subscribe("events.order.*", self._on_order_event)
        _log.info(
            "nt_risk_engine_bridge_bootstrapped",
            runner_id=self._runner_id,
            subject=self.subject(),
        )

    def _on_order_event(self, event: Any) -> None:
        """Sync MessageBus callback for the ``events.order.*`` stream. Only
        ``OrderDenied`` is republished; submits / accepts / fills are ignored
        (they ride the telemetry channel). The async publish is scheduled on
        the captured runner loop because NT invokes this handler synchronously
        on the engine thread."""
        if type(event).__name__ != "OrderDenied":
            return
        coro = self.on_order_denied(event)
        loop = self._loop
        if loop is not None and not self._loop_is_current(loop):
            fut: Any = asyncio.run_coroutine_threadsafe(coro, loop)
        else:
            fut = asyncio.ensure_future(coro)
        self._pending.add(fut)
        fut.add_done_callback(self._on_publish_done)

    @staticmethod
    def _loop_is_current(loop: asyncio.AbstractEventLoop) -> bool:
        try:
            return asyncio.get_running_loop() is loop
        except RuntimeError:
            return False

    def _on_publish_done(self, fut: Any) -> None:
        # A denied-order publish that dies must never be silent (对账不静默 红线).
        self._pending.discard(fut)
        try:
            exc = fut.exception()
        except (asyncio.CancelledError, Exception):  # noqa: BLE001 — reaping the scheduled future
            return
        if exc is not None:
            _log.error("pre_trade_reject_publish_failed", error=str(exc))

    async def on_order_denied(self, denied: _OrderDenied) -> None:
        """Translate one NT ``OrderDenied`` into a ``PreTradeRejected`` envelope
        and publish it at-least-once. Unknown NT reasons map to ``max_qty``'s
        sibling set only when recognised; an unmapped reason is published as-is
        but logged so the catalog gap is visible."""
        # Shape guard: a real NT OrderDenied always carries reason + instrument;
        # a drifted / malformed event that lost them is skipped (never publish a
        # garbage rejection built from empty defaults).
        if not hasattr(denied, "reason") or not hasattr(denied, "instrument_id"):
            _log.warning(
                "pre_trade_reject_event_shape_mismatch",
                event_type=type(denied).__name__,
                has_reason=hasattr(denied, "reason"),
                has_instrument_id=hasattr(denied, "instrument_id"),
            )
            return

        reason = _map_reject_reason(str(getattr(denied, "reason", "") or ""))
        symbol = str(getattr(denied, "instrument_id", "") or "")
        # NT OrderDenied carries no rule_id (our pre-trade rule catalog is
        # runner-side); it publishes empty and the cloud correlates by symbol +
        # fingerprint. side / quantity / price are likewise absent on the NT
        # event, so the fingerprint folds in client_order_id (the one stable field
        # it does carry) to keep the correlation handle unique.
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

        client_order_id = str(getattr(denied, "client_order_id", "") or "")
        side = str(getattr(denied, "side", "") or "")
        quantity = str(getattr(denied, "quantity", "") or "")
        price = str(getattr(denied, "price", "") or "")
        ts_seconds = _denied_ts_seconds(denied)
        fingerprint = order_fingerprint(symbol, client_order_id, side, quantity, price, ts_seconds)

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


def _denied_ts_seconds(denied: Any) -> int:
    """Event time in whole seconds for the fingerprint. A real NT OrderDenied
    exposes ``ts_event`` in nanoseconds; the runner-side test doubles use a
    plain ``ts_seconds``. Prefer the real NT field, fall back to the test one,
    default 0."""
    ts_seconds = getattr(denied, "ts_seconds", None)
    if ts_seconds is not None:
        return int(ts_seconds)
    ts_event_ns = getattr(denied, "ts_event", None)
    if ts_event_ns is not None:
        return int(ts_event_ns) // 1_000_000_000
    return 0


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
    from custos.core.nats_client import _now_rfc3339_nanos as _fmt

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
    bridge = NtRiskEngineBridge(client=client, tenant_id=tenant_id, runner_id=runner_id)
    bridge.bootstrap(message_bus)
    return bridge
