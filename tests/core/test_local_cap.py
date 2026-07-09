"""Runner notional cap — threshold, Decimal parsing, floor fallback, and the
disconnect-resilient reject path (red line 0.3 soft limit)."""

from __future__ import annotations

from decimal import Decimal

from custos.core.local_cap import (
    LIVE_CAP_FLOOR_USD,
    PAPER_CAP_FLOOR_USD,
    LocalCapConfig,
    RunnerNotionalCap,
    check_cap,
)


def _cfg(cap: str = "1000") -> LocalCapConfig:
    return LocalCapConfig(max_notional_per_runner=Decimal(cap))


def test_local_cap_rejects_over_threshold() -> None:
    assert check_cap(Decimal("900"), Decimal("200"), _cfg("1000")) is False


def test_local_cap_allows_under_threshold() -> None:
    assert check_cap(Decimal("500"), Decimal("200"), _cfg("1000")) is True


def test_local_cap_config_parses_decimal_not_float() -> None:
    cfg = LocalCapConfig.from_spec(
        {"risk_config": {"max_notional_per_runner": "1234.56"}}, live=True
    )
    assert isinstance(cfg.max_notional_per_runner, Decimal)
    assert cfg.max_notional_per_runner == Decimal("1234.56")


def test_local_cap_falls_back_to_floor_when_spec_missing() -> None:
    paper = LocalCapConfig.from_spec({}, live=False)
    live = LocalCapConfig.from_spec({}, live=True)
    assert paper.max_notional_per_runner == PAPER_CAP_FLOOR_USD
    assert live.max_notional_per_runner == LIVE_CAP_FLOOR_USD


async def test_cap_exceeded_emits_pre_trade_rejected() -> None:
    """A breach publishes a PreTradeRejected (reject_reason=max_notional) on the
    pre-trade reject channel, using the real risk-edge publisher."""
    from custos.engines.nautilus.risk import make_runner_cap_reject_publisher

    published: list = []

    class _FakeClient:
        async def publish_telemetry_envelope(self, subject: str, envelope) -> None:
            published.append((subject, envelope))

    publisher = make_runner_cap_reject_publisher(
        client=_FakeClient(),  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id="r1",
    )
    guard = RunnerNotionalCap(_cfg("1000"), reject_publisher=publisher)

    allowed = await guard.allows(
        symbol="BTCUSDT", current_open=Decimal("900"), new_order_notional=Decimal("200")
    )

    assert allowed is False
    assert len(published) == 1
    subject, envelope = published[0]
    assert subject == "arx.acme.pre_trade_reject.r1"
    assert envelope.payload["reject_reason"] == "max_notional"
    assert envelope.payload["rule_id"] == "runner_notional_cap"
    assert envelope.payload["symbol"] == "BTCUSDT"


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
