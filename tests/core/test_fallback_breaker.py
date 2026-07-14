from decimal import Decimal

from custos.core.fallback_breaker import FallbackBreaker, FallbackBreakerConfig


def test_breaker_freezes_on_instance_notional_breach() -> None:
    breaker = FallbackBreaker(
        FallbackBreakerConfig(max_notional=Decimal("10"), max_drawdown_pct=Decimal("20"))
    )
    verdict = breaker.evaluate(open_notional=Decimal("11"))
    assert verdict.tripped
    assert verdict.reason == "notional_breach"
    assert breaker.frozen


def test_config_refresh_does_not_clear_frozen_state() -> None:
    breaker = FallbackBreaker(
        FallbackBreakerConfig(max_notional=Decimal("10"), max_drawdown_pct=Decimal("20"))
    )
    breaker.evaluate(open_notional=Decimal("11"))
    breaker.apply_config(
        FallbackBreakerConfig(max_notional=Decimal("20"), max_drawdown_pct=Decimal("30"))
    )
    assert breaker.frozen
