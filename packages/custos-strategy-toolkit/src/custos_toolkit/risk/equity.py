# shared/risk/equity.py
"""Risk-control equity resolution (platform-agnostic).

Resolves the mark-to-market equity value used for risk-control decisions
(drawdown / daily-loss / peak tracking). Any unreliable equity input falls back
to the free balance with an explicit warn reason (lesson #15: fail-safe, never
silent). Depends only on ``decimal`` so it stays platform-agnostic and unit
testable without nautilus (lesson #22).
"""

from decimal import Decimal
from typing import cast


def resolve_risk_equity(
    equity_value: Decimal | None,
    understated: bool,
    free_balance: Decimal,
    last_good: Decimal | None = None,
) -> tuple[Decimal, str | None]:
    """Resolve the equity used for risk control with a fail-safe, conservative fallback.

    The reliable path returns the mark-to-market equity and ``warn_reason is None`` —
    that signal lets the caller remember it as a conservative floor for later ticks.

    On any unreliable path the free balance alone is *optimistic* (it excludes
    unrealized loss), so using it would relax drawdown / daily-loss exactly when a
    position is underwater. Instead we take the most conservative of the free balance
    and the last reliable mark, so a developing loss captured before a price gap is not
    erased (fail-safe, never fail-open).

    Args:
        equity_value: Mark-to-market equity (account total + unrealized PnL), or
            None if the portfolio could not produce one for the quote currency.
        understated: True when at least one open position could not be priced, so
            ``equity_value`` is unreliable.
        free_balance: Available (free) quote-currency balance.
        last_good: The most recent reliable mark-to-market equity, if any.

    Returns:
        ``(resolved_equity, warn_reason)``. ``warn_reason`` is None on the reliable
        path; otherwise it is a non-empty reason describing the unreliable input.
    """
    # A reliable mark is a fully-priced, finite, positive equity value. is_finite()
    # must precede the comparison: ``Decimal("NaN") <= 0`` raises InvalidOperation.
    reliable = (
        not understated
        and equity_value is not None
        and equity_value.is_finite()
        and equity_value > 0
    )
    if reliable:
        return cast(Decimal, equity_value), None

    # Unreliable: floor by the most conservative of {free balance, last good mark}.
    conservative = free_balance
    if last_good is not None and last_good.is_finite() and last_good > 0:
        conservative = min(conservative, last_good)

    if understated:
        reason = "equity understated (unpriced open positions); using conservative risk equity"
    elif equity_value is None:
        reason = "equity unavailable (no value for quote currency); using conservative risk equity"
    else:
        reason = f"equity invalid ({equity_value}); using conservative risk equity"
    return conservative, reason
