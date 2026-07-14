# shared/filters/volatility.py
"""
Volatility-based trading filter.

Filters trades based on ATR (Average True Range) as a percentage of price.
"""

from collections import deque

from ..config._values import config_value
from ..protocols.bar import BarProtocol
from ..protocols.filter import FilterResult
from .base import BaseFilter
from .registry import register_filter


@register_filter("volatility")
class VolatilityFilter(BaseFilter):
    """
    Filter trades by ATR percentage.

    Blocks trades when volatility (ATR/price) is outside the configured range.
    This helps avoid trading in either too quiet or too volatile markets.

    All ratio values use decimal fractions (e.g. 0.003 = 0.3%), matching
    base_config.yaml and the platform adapter layers (CR-3, fix plan 04).

    Config options:
        enabled: bool - Whether filter is active (default True)
        atr_lookback: int - Period for ATR calculation (default 14)
        min_atr_pct: float - Minimum ATR/price as decimal fraction (default 0.003)
        max_atr_pct: float - Maximum ATR/price as decimal fraction (default 0.05)
    """

    @property
    def name(self) -> str:
        return "volatility"

    def __init__(self, config: dict[str, object]):
        super().__init__(config)
        self.enabled = config_value(config, "enabled", True)
        self.atr_lookback = config_value(config, "atr_lookback", 14)
        self.min_atr_pct = config_value(config, "min_atr_pct", 0.003)
        self.max_atr_pct = config_value(config, "max_atr_pct", 0.05)

        # State for ATR calculation
        self._prev_close: float | None = None
        self._tr_values: deque[float] = deque(maxlen=self.atr_lookback)
        self._atr: float | None = None
        self._ready = False

    def _calculate_true_range(self, bar: BarProtocol) -> float:
        """
        Calculate True Range for a bar.

        True Range is the maximum of:
        - High - Low
        - |High - Previous Close|
        - |Low - Previous Close|

        Args:
            bar: Current bar data

        Returns:
            True range value
        """
        high = float(bar.high)
        low = float(bar.low)
        high_low = high - low

        if self._prev_close is not None:
            high_close = abs(high - self._prev_close)
            low_close = abs(low - self._prev_close)
            return max(high_low, high_close, low_close)
        return high_low

    def update(self, bar: BarProtocol) -> None:
        """
        Update ATR calculation with new bar data.

        Args:
            bar: Current bar data
        """
        # Calculate and store true range
        tr = self._calculate_true_range(bar)
        self._tr_values.append(tr)

        # Update previous close for next calculation
        self._prev_close = float(bar.close)

        # Calculate ATR as simple moving average of TR values
        if len(self._tr_values) >= self.atr_lookback:
            self._atr = sum(self._tr_values) / len(self._tr_values)
            self._ready = True

    def check(self, bar: BarProtocol) -> FilterResult:
        """
        Check if current volatility is within acceptable range.

        Args:
            bar: Current bar data

        Returns:
            FilterResult indicating pass/fail
        """
        if not self.enabled:
            return FilterResult.allow()

        if not self._ready or self._atr is None:
            return FilterResult.block("ATR not yet calculated (warming up)")

        price = float(bar.close)
        if price <= 0:
            return FilterResult.block("Invalid price (zero or negative)")

        # Decimal fraction (0.006 = 0.6%) — same unit as config (CR-3).
        atr_pct = self._atr / price

        if atr_pct < self.min_atr_pct:
            return FilterResult.block(
                f"Volatility too low: ATR {atr_pct:.4f} < min {self.min_atr_pct}"
            )

        if atr_pct > self.max_atr_pct:
            return FilterResult.block(
                f"Volatility too high: ATR {atr_pct:.4f} > max {self.max_atr_pct}"
            )

        return FilterResult.allow()

    def reset(self) -> None:
        """Reset filter state."""
        self._prev_close = None
        self._tr_values.clear()
        self._atr = None
        self._ready = False

    def get_atr(self) -> float | None:
        """
        Get current ATR value.

        Returns:
            Current ATR or None if not yet calculated
        """
        return self._atr

    def get_atr_pct(self, price: float) -> float | None:
        """
        Get ATR as decimal fraction of given price (0.006 = 0.6%).

        Args:
            price: Reference price

        Returns:
            ATR fraction or None if not yet calculated
        """
        if self._atr is None or price <= 0:
            return None
        return self._atr / price
