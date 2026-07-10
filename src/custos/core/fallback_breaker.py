"""Runner fallback breaker — the disconnect-resilient hard limit.

Where the notional cap softly refuses *new* orders, the breaker is the last
line: once total open notional or peak-to-current drawdown breaches its ceiling
it trips, which flattens positions and freezes further orders until an operator
intervenes. It keeps evaluating while the cloud is unreachable so a runaway
runner is contained locally (the disconnect-resilient red line).

All money math is ``Decimal`` (red line 0.4). Peak equity is tracked as Decimal
— never copy a float high-water mark. The drawdown breach needs an equity feed;
when equity is not supplied the breaker still enforces the notional ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from custos.core.log import get_logger

_log = get_logger("custos.fallback_breaker")

# Structural hard-limit fallbacks used when the cloud spec carries no explicit
# breaker config. Deliberately conservative — an operator raises them via
# risk_config once a runner is trusted.
DEFAULT_MAX_NOTIONAL_USD = Decimal("1000")
DEFAULT_MAX_DRAWDOWN_PCT = Decimal("20")


@dataclass(frozen=True)
class FallbackBreakerConfig:
    """Hard-limit ceilings. ``max_drawdown_pct`` is a percentage (e.g. 20 = 20%)."""

    max_notional: Decimal
    max_drawdown_pct: Decimal

    @classmethod
    def from_spec(cls, spec: dict) -> FallbackBreakerConfig:
        """Resolve from a ``DeploymentSpec`` dict's
        ``risk_config.fallback_breaker`` block, falling back to conservative
        defaults. Parsed via ``Decimal(str(...))`` (red line 0.4)."""
        raw = spec.get("risk_config", {}).get("fallback_breaker", {})
        max_notional = raw.get("max_notional")
        max_drawdown_pct = raw.get("max_drawdown_pct")
        return cls(
            max_notional=Decimal(str(max_notional))
            if max_notional is not None
            else DEFAULT_MAX_NOTIONAL_USD,
            max_drawdown_pct=Decimal(str(max_drawdown_pct))
            if max_drawdown_pct is not None
            else DEFAULT_MAX_DRAWDOWN_PCT,
        )


@dataclass(frozen=True)
class BreakerVerdict:
    """Outcome of one breaker evaluation. ``reason`` is the breach that tripped
    it (``notional_breach`` / ``drawdown_breach``) or None when within limits."""

    tripped: bool
    reason: str | None
    drawdown_pct: Decimal


class FallbackBreaker:
    """Stateful runner hard limit. ``evaluate`` checks the current exposure and
    trips (and stays frozen) on the first breach; ``allows_new_orders`` reflects
    the freeze."""

    def __init__(self, config: FallbackBreakerConfig) -> None:
        self._config = config
        # Decimal high-water mark — never a float (red line 0.4).
        self._peak_equity: Decimal = Decimal("0")
        self._frozen = False

    @property
    def frozen(self) -> bool:
        return self._frozen

    def apply_config(self, new_config: FallbackBreakerConfig) -> bool:
        """Swap the enforced ceilings. Returns True when the value actually
        changed. Peak equity + frozen state are preserved so a refresh does
        not silently reset the drawdown high-water mark or clear an existing
        trip — cloud-side edits raise / lower the limits, they don't reset
        the breaker."""
        if new_config == self._config:
            return False
        self._config = new_config
        return True

    def allows_new_orders(self) -> bool:
        return not self._frozen

    def evaluate(
        self,
        *,
        open_notional: Decimal,
        current_equity: Decimal | None = None,
    ) -> BreakerVerdict:
        drawdown_pct = Decimal("0")
        if current_equity is not None:
            if current_equity > self._peak_equity:
                self._peak_equity = current_equity
            drawdown_pct = self._drawdown_pct(current_equity)

        reason: str | None = None
        if open_notional > self._config.max_notional:
            reason = "notional_breach"
        elif current_equity is not None and drawdown_pct > self._config.max_drawdown_pct:
            reason = "drawdown_breach"

        if reason is not None and not self._frozen:
            self._frozen = True
            _log.warning(
                "fallback_breaker_tripped",
                reason=reason,
                open_notional=str(open_notional),
                drawdown_pct=str(drawdown_pct),
                max_notional=str(self._config.max_notional),
                max_drawdown_pct=str(self._config.max_drawdown_pct),
            )
        return BreakerVerdict(tripped=reason is not None, reason=reason, drawdown_pct=drawdown_pct)

    def _drawdown_pct(self, current_equity: Decimal) -> Decimal:
        if self._peak_equity <= 0:
            return Decimal("0")
        return (self._peak_equity - current_equity) / self._peak_equity * Decimal("100")
