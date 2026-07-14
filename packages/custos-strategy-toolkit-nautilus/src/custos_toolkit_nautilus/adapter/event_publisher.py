"""Strategy event publishing helper.

Publishes strategy events as **bytes** (raw UTF-8 JSON) through the
NautilusTrader MessageBus native external-streaming path. When the runner builds a
db-backed msgbus (``database.enabled=true``), ``publish()`` auto-writes to the Redis
stream ``events`` with fields ``{topic, payload}``; consumers do one-layer
``json.loads``. ``bytes`` payloads are single-encoded — ``str`` would be
double-encoded under ``encoding=json``. External Redis publication additionally
depends on the runner's database config; the deployment precondition
(``database.enabled=true``) is covered by docs/ops/d2-msgbus-migration-runbook.md.

Controlled by EVENT_PUBLISHING_ENABLED env var (default off).

signal_id and tag helpers are inlined here (uuid4 + "signal_id:" prefix)
to avoid shared/ -> deploy/ cross-package dependency.
deploy/sidecar/events/signal_id.py is the canonical sidecar-side implementation;
both sides inline the same prefix constant and uuid4 logic, staying independent
but compatible.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import Iterable
from typing import Protocol, cast

from .runtime_types import Clock, MessageBus, Order

logger = logging.getLogger(__name__)

# MessageBus topic (all strategy events written to one topic)
EVENT_TOPIC = "strategy.events"

# signal_id tag prefix (matches deploy/sidecar/events/signal_id.py SIGNAL_ID_PREFIX)
_SIGNAL_ID_TAG_PREFIX = "signal_id:"


def resolve_event_strategy_id(fallback: str) -> str:
    """Resolve the strategy_id used for published events.

    The event strategy_id must be the Crucible-assigned slug (``STRATEGY_ID`` env, same
    source as the sidecar's `_persist_*_to_crucible`), not the NautilusTrader internal id
    (``self.id.value``, e.g. ``SuperTrendStrategy-000``). The latter makes the Crucible
    EventPersister upsert hit ``orders_strategy_id_fkey`` -> the whole SSE persistence
    path dies silently. Falls back to ``fallback`` when the env is unset/blank.
    """
    env_value = (os.environ.get("STRATEGY_ID") or "").strip()
    return env_value or fallback


def strategy_id_env_missing() -> bool:
    """Return True when the STRATEGY_ID env is unset/blank.

    In that case ``resolve_event_strategy_id`` falls back to the Nautilus internal id, so
    published events' strategy_id hits the Crucible FK -> Path B is all silently dropped.
    The caller (on_start) uses this to warn when publishing is enabled, preventing that FK
    conflict from silently recurring via the fallback.
    """
    return not (os.environ.get("STRATEGY_ID") or "").strip()


def generate_signal_id() -> str:
    """Generate a unique signal_id (UUID4)."""
    return str(uuid.uuid4())


def make_signal_tag(signal_id: str) -> str:
    """Wrap signal_id as an order tag string."""
    return f"{_SIGNAL_ID_TAG_PREFIX}{signal_id}"


def extract_signal_id_from_tags(tags: Iterable[object] | None) -> str | None:
    """Extract signal_id from order tags.

    Args:
        tags: NautilusTrader order.tags (may be list[str] or other iterable)
    """
    if not tags:
        return None
    for tag in tags:
        tag_str = str(tag)
        if tag_str.startswith(_SIGNAL_ID_TAG_PREFIX):
            return tag_str[len(_SIGNAL_ID_TAG_PREFIX) :]
    return None


def _compute_fill_latency_ms(event: object, order: object) -> int | None:
    """Submit->fill latency (ms) from nautilus nanosecond timestamps.

    The submit anchor prefers order.ts_submitted (when the order was sent to the venue),
    falling back to ts_init when not submitted. Missing timestamps or a fill earlier than
    the submit (clock anomaly) -> None. event/order are accessed via duck typing, so this
    module stays independently testable without a nautilus dependency.
    """
    submit_ns = cast(int, getattr(order, "ts_submitted", 0) or getattr(order, "ts_init", 0))
    fill_ns = cast(int, getattr(event, "ts_event", 0))
    try:
        if not submit_ns or not fill_ns or fill_ns < submit_ns:
            return None
        return (fill_ns - submit_ns) // 1_000_000
    except TypeError:
        # Non-numeric timestamps yield no latency rather than aborting the publish.
        return None


class _NamedValue(Protocol):
    @property
    def name(self) -> str: ...


class _OrderEvent(Protocol):
    @property
    def client_order_id(self) -> object: ...
    @property
    def instrument_id(self) -> object: ...
    @property
    def venue_order_id(self) -> object | None: ...


class _PositionEvent(Protocol):
    @property
    def entry(self) -> _NamedValue: ...
    @property
    def instrument_id(self) -> object: ...
    @property
    def position_id(self) -> object: ...
    @property
    def quantity(self) -> object: ...


class EventPublisher:
    """Strategy event publisher.

    Args:
        msgbus: NautilusTrader MessageBus instance (strategy.msgbus)
        strategy_id: Strategy ID string
        clock: NautilusTrader Clock instance (for timestamps)
        enabled: Whether event publishing is enabled (config switch)
    """

    def __init__(
        self,
        msgbus: MessageBus | None,
        strategy_id: str,
        clock: Clock | None = None,
        enabled: bool = False,
    ) -> None:
        self._msgbus = msgbus
        self._strategy_id = strategy_id
        self._clock = clock
        self._enabled = enabled
        # Observable no-publish failure semantics. ``dropped_events`` counts
        # events that could NOT be published (msgbus unavailable or publish
        # raised) so the silent-drop path is detectable, not invisible.
        self.dropped_events = 0
        self._no_msgbus_logged = False
        if enabled and msgbus is None:
            logger.error(
                "EventPublisher enabled but msgbus is None — events will NOT be "
                "published (check strategy msgbus injection)."
            )
            self._no_msgbus_logged = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _timestamp(self) -> str:
        if self._clock:
            return str(self._clock.timestamp_ns())
        return ""

    def _publish(self, data: dict[str, object]) -> None:
        if not self._enabled:
            return
        if self._msgbus is None:
            # H3: enabled but no msgbus → cannot publish externally. Non-silent:
            # count every drop, log once (avoid spam) at ERROR.
            self.dropped_events += 1
            if not self._no_msgbus_logged:
                logger.error("EventPublisher: msgbus unavailable, event dropped (not published).")
                self._no_msgbus_logged = True
            return
        try:
            data["event_id"] = str(uuid.uuid4())
            data["timestamp"] = self._timestamp()
            data["strategy_id"] = self._strategy_id
            # raw JSON as bytes via nautilus msgbus native external streaming
            # (bytes single-encoded; str double-encodes under encoding=json).
            payload = json.dumps(data).encode("utf-8")
            self._msgbus.publish(EVENT_TOPIC, payload)
        except Exception as exc:
            self.dropped_events += 1
            logger.warning("Event publish failed: %s", exc)

    def publish_signal(
        self,
        signal_id: str,
        direction: str,
        pair: str,
        price: str,
        strength: float,
        metadata: dict[str, object] | None = None,
        stop_loss: str | None = None,
        take_profit: str | None = None,
    ) -> None:
        """Publish a signal event.

        stop_loss/take_profit are optional (SuperTrend computes the SL only after entry,
        so it's usually unknown at signal time; it can be backfilled after entry executes).
        Older callers that omit them get None -- backward compatible.
        """
        self._publish(
            {
                "type": "signal",
                "signal_id": signal_id,
                "direction": direction,
                "pair": pair,
                "price": price,
                "strength": strength,
                "metadata": metadata,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }
        )

    def publish_order(
        self,
        order_id: str,
        signal_id: str | None,
        venue_order_id: str | None,
        instrument: str,
        side: str,
        order_type: str,
        quantity: str,
        fill_price: str | None,
        status: str,
        trigger_price: str | None = None,
        reduce_only: bool = False,
        price: str | None = None,
        fill_latency_ms: int | None = None,
    ) -> None:
        """Publish an order lifecycle event.

        trigger_price (STOP order trigger) + reduce_only are optional; older callers that
        omit them get None/False -- backward compatible with Crucible OrderEvent's default
        fields. price (LIMIT order price) is optional, letting Crucible signals derive a
        take_profit from a reduce_only LIMIT order.price; older callers get None.
        fill_latency_ms (submit->fill latency, ms) is carried only on filled orders for
        Crucible infra/tca execution-quality analysis; older callers get None.
        """
        self._publish(
            {
                "type": "order",
                "order_id": order_id,
                "signal_id": signal_id,
                "venue_order_id": venue_order_id,
                "instrument": instrument,
                "side": side,
                "order_type": order_type,
                "quantity": quantity,
                "fill_price": fill_price,
                "status": status,
                "trigger_price": trigger_price,
                "reduce_only": reduce_only,
                "price": price,
                "fill_latency_ms": fill_latency_ms,
            }
        )

    def publish_position(
        self,
        position_id: str | None,
        signal_id: str | None,
        instrument: str,
        side: str,
        quantity: str,
        realized_pnl: str | None,
        status: str,
    ) -> None:
        """Publish a position change event."""
        self._publish(
            {
                "type": "position",
                "position_id": position_id,
                "signal_id": signal_id,
                "instrument": instrument,
                "side": side,
                "quantity": quantity,
                "realized_pnl": realized_pnl,
                "status": status,
            }
        )

    # ── nautilus event/order field cohesion ────────────────────────────────────
    # Converge the "common field extraction" that each on_order_*/on_position_* callback
    # repeats verbatim into one place: callers pass only the fields that genuinely vary by
    # callback (side/order_type/quantity/fill_price/status), while the common boilerplate
    # (order_id/venue_order_id/instrument/trigger_price/reduce_only/price) is extracted here.
    # Never raises -- an extraction or publish failure only counts dropped_events, never
    # affecting the caller's money/cleanup path. event/order are accessed via duck typing
    # (getattr/attributes), so this module stays independently testable without nautilus.

    def publish_order_event(
        self,
        *,
        event: _OrderEvent,
        order: Order | None,
        signal_id: str | None,
        side: str,
        order_type: str,
        quantity: str,
        status: str,
        fill_price: str | None = None,
        include_price: bool = False,
        venue_from_event: bool = True,
    ) -> None:
        """Extract common fields from a nautilus order event + order and publish it.

        include_price: only accepted/filled carry the LIMIT order price (for Crucible to
            derive take_profit); canceled/rejected omit it by default (current behavior).
        venue_from_event: accepted/filled/canceled read venue_order_id from the event;
            rejected/cancel_rejected set False (a reject has no valid venue id, always None).
        """
        try:
            # Submit->fill latency only matters for filled orders
            # (accepted/canceled/rejected have no fill).
            fill_latency_ms = (
                _compute_fill_latency_ms(event, order)
                if status == "filled" and order is not None
                else None
            )
            self.publish_order(
                order_id=str(event.client_order_id),
                signal_id=signal_id,
                venue_order_id=(
                    str(event.venue_order_id)
                    if venue_from_event and getattr(event, "venue_order_id", None)
                    else None
                ),
                instrument=str(event.instrument_id),
                side=side,
                order_type=order_type,
                quantity=quantity,
                fill_price=fill_price,
                status=status,
                trigger_price=(
                    str(order.trigger_price)
                    if order is not None and getattr(order, "trigger_price", None)
                    else None
                ),
                reduce_only=(
                    bool(getattr(order, "is_reduce_only", False)) if order is not None else False
                ),
                price=(
                    str(order.price)
                    if include_price and order is not None and getattr(order, "price", None)
                    else None
                ),
                fill_latency_ms=fill_latency_ms,
            )
        except Exception as exc:
            self.dropped_events += 1
            logger.warning("publish_order_event extraction failed: %s", exc)

    def publish_position_event(
        self,
        *,
        event: _PositionEvent,
        signal_id: str | None,
        status: str,
        realized_pnl: str | None = None,
    ) -> None:
        """Extract common position-event fields (id/instrument/side/quantity) and publish."""
        try:
            self.publish_position(
                position_id=str(event.position_id) if hasattr(event, "position_id") else None,
                signal_id=signal_id,
                instrument=str(event.instrument_id),
                side=event.entry.name if hasattr(event, "entry") else "UNKNOWN",
                quantity=str(event.quantity) if hasattr(event, "quantity") else "0",
                realized_pnl=realized_pnl,
                status=status,
            )
        except Exception as exc:
            self.dropped_events += 1
            logger.warning("publish_position_event extraction failed: %s", exc)
