# shared/filters/regime.py
"""
Market regime detection filter.

Detects whether the market is trending or ranging and filters
trades based on the detected regime.
"""

from collections import deque

from ..protocols.bar import BarProtocol
from ..protocols.filter import FilterResult
from .base import BaseFilter
from .registry import register_filter


@register_filter("regime")
class RegimeFilter(BaseFilter):
    """
    Filter trades based on detected market regime.

    Uses price history to classify the market as trending or ranging,
    then allows or blocks trades based on the configured regime preference.

    Config options:
        enabled: bool - Whether filter is active (default True)
        lookback: int - Number of bars for regime detection (default 20)
        method: str - Detection method: "efficiency_ratio" or "atr_percentile" (default "efficiency_ratio")
        trending_threshold: float - Threshold for trending detection (default 0.5)
        allow_regime: str - Which regime to allow: "trending", "ranging", or "both" (default "trending")
    """

    @property
    def name(self) -> str:
        return "regime"

    def __init__(self, config: dict):
        super().__init__(config)
        self.enabled = config.get("enabled", True)
        self.lookback = config.get("lookback", 20)
        self.method = config.get("method", "efficiency_ratio")
        self.trending_threshold = config.get("trending_threshold", 0.5)
        self.allow_regime = config.get("allow_regime", "trending")

        # Validate method
        valid_methods = ("efficiency_ratio", "atr_percentile")
        if self.method not in valid_methods:
            raise ValueError(f"Invalid method '{self.method}'. Must be one of: {valid_methods}")

        # Validate allow_regime
        valid_regimes = ("trending", "ranging", "both")
        if self.allow_regime not in valid_regimes:
            raise ValueError(
                f"Invalid allow_regime '{self.allow_regime}'. Must be one of: {valid_regimes}"
            )

        # Price history for regime detection
        self._prices: deque[float] = deque(maxlen=self.lookback)
        self._current_regime: str = "unknown"
        self._ready = False

    def update(self, bar: BarProtocol) -> None:
        """
        Update filter state with new bar data.

        Appends close price to history and recalculates regime.
        """
        self._prices.append(bar.close)

        # Check if we have enough data
        if len(self._prices) >= self.lookback:
            self._ready = True
            self._current_regime = self._calculate_regime()
        else:
            self._ready = False
            self._current_regime = "unknown"

    def _calculate_regime(self) -> str:
        """
        Calculate current market regime based on price history.

        Returns:
            "trending", "ranging", or "unknown"
        """
        prices = list(self._prices)

        if self.method == "efficiency_ratio":
            return self._calculate_efficiency_ratio(prices)
        elif self.method == "atr_percentile":
            return self._calculate_atr_percentile(prices)

        return "unknown"

    def _calculate_efficiency_ratio(self, prices: list[float]) -> str:
        """
        Calculate regime using efficiency ratio method.

        Efficiency ratio = net price change / sum of absolute changes
        High efficiency (> threshold) indicates trending market.
        Low efficiency (< threshold) indicates ranging market.
        """
        if len(prices) < 2:
            return "unknown"

        net_change = abs(prices[-1] - prices[0])
        total_change = sum(abs(prices[i] - prices[i - 1]) for i in range(1, len(prices)))

        if total_change > 0:
            efficiency = net_change / total_change
            return "trending" if efficiency >= self.trending_threshold else "ranging"

        return "unknown"

    def _calculate_atr_percentile(self, prices: list[float]) -> str:
        """
        Calculate regime using ATR percentile method.

        Compares price range to average price.
        High range percentage (> threshold) indicates trending market.
        """
        if len(prices) < 2:
            return "unknown"

        price_range = max(prices) - min(prices)
        avg_price = sum(prices) / len(prices)

        if avg_price > 0:
            range_pct = price_range / avg_price
            return "trending" if range_pct >= self.trending_threshold else "ranging"

        return "unknown"

    def check(self, bar: BarProtocol) -> FilterResult:
        """
        Check if current regime allows trading.

        Args:
            bar: Current bar data (not used directly, regime is pre-calculated)

        Returns:
            FilterResult indicating pass/fail based on regime
        """
        if not self.enabled:
            return FilterResult.allow()

        if not self._ready:
            return FilterResult.block(
                f"Insufficient data ({len(self._prices)}/{self.lookback} bars)"
            )

        # Allow both regimes
        if self.allow_regime == "both":
            return FilterResult.allow()

        # Check if current regime matches allowed regime
        if self._current_regime == self.allow_regime:
            return FilterResult.allow()

        return FilterResult.block(
            f"Regime '{self._current_regime}' not allowed (requires '{self.allow_regime}')"
        )

    def get_current_regime(self) -> str:
        """
        Get the current detected market regime.

        Returns:
            "trending", "ranging", or "unknown"
        """
        return self._current_regime

    def get_efficiency_ratio(self) -> float | None:
        """
        Get the current efficiency ratio (if method is efficiency_ratio).

        Returns:
            Efficiency ratio value or None if not calculable
        """
        if len(self._prices) < self.lookback:
            return None

        prices = list(self._prices)
        net_change = abs(prices[-1] - prices[0])
        total_change = sum(abs(prices[i] - prices[i - 1]) for i in range(1, len(prices)))

        if total_change > 0:
            return net_change / total_change
        return None
