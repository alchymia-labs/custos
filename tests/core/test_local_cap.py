"""Runner notional cap — threshold, Decimal parsing, floor fallback, and the
disconnect-resilient reject path (red line 0.3 soft limit)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from custos.core.local_cap import (
    LocalCapConfig,
    RunnerNotionalCap,
    RunnerSafetyPolicyUnavailableError,
    check_cap,
)


def _cfg(order: str = "1000", total: str | None = None) -> LocalCapConfig:
    return LocalCapConfig(
        max_order_notional=Decimal(order),
        max_total_notional=Decimal(total or order),
        settlement_currency="USDT",
        policy_id=None,
        policy_digest=None,
        owner_policy=False,
        source="test_only",
    )


def test_local_cap_rejects_over_threshold() -> None:
    assert check_cap(Decimal("900"), Decimal("200"), _cfg("1000")) is False


def test_local_cap_allows_under_threshold() -> None:
    assert check_cap(Decimal("500"), Decimal("200"), _cfg("1000")) is True


def test_local_cap_config_keeps_decimal_limits() -> None:
    cfg = _cfg("1234.56", "2345.67")
    assert isinstance(cfg.max_order_notional, Decimal)
    assert cfg.max_order_notional == Decimal("1234.56")
    assert cfg.max_total_notional == Decimal("2345.67")


def test_local_cap_fallback_is_explicit_non_live_and_live_fails_closed() -> None:
    sandbox = LocalCapConfig.strictest_local_fallback("sandbox")
    assert sandbox.max_order_notional == Decimal("50")
    assert sandbox.max_total_notional == Decimal("200")
    assert sandbox.owner_policy is False
    with pytest.raises(RunnerSafetyPolicyUnavailableError):
        LocalCapConfig.strictest_local_fallback("live")


async def test_cap_exceeded_invokes_injected_fact_sink() -> None:
    published: list[tuple[str, Decimal, Decimal, Decimal]] = []

    async def publisher(
        symbol: str,
        current_open: Decimal,
        requested_notional: Decimal,
        cap: Decimal,
    ) -> None:
        published.append((symbol, current_open, requested_notional, cap))

    guard = RunnerNotionalCap(_cfg("1000"), reject_publisher=publisher)

    allowed = await guard.allows(
        symbol="BTCUSDT", current_open=Decimal("900"), new_order_notional=Decimal("200")
    )

    assert allowed is False
    assert published == [("BTCUSDT", Decimal("900"), Decimal("200"), Decimal("1000"))]


async def test_cap_exceeded_during_disconnect_still_rejects() -> None:
    """The local reject decision must hold even when the cloud notification
    fails (red line 0.3): the cap keeps protecting while disconnected."""

    async def _publish_fails(*_args) -> None:
        raise ConnectionError("nats disconnected")

    guard = RunnerNotionalCap(_cfg("1000"), reject_publisher=_publish_fails)

    allowed = await guard.allows(
        symbol="BTCUSDT", current_open=Decimal("900"), new_order_notional=Decimal("200")
    )

    assert allowed is False


async def test_cap_is_live_guard_relaxed_double() -> None:
    """With no breaker and no publisher present at all, the cap must still fire
    on its own — proving it is an independent live guard, not a dead branch that
    only trips because another layer runs."""
    guard = RunnerNotionalCap(_cfg("1000"))

    breached = await guard.allows(
        symbol="ETHUSDT", current_open=Decimal("1000"), new_order_notional=Decimal("1")
    )
    within = await guard.allows(
        symbol="ETHUSDT", current_open=Decimal("100"), new_order_notional=Decimal("1")
    )

    assert breached is False
    assert within is True
