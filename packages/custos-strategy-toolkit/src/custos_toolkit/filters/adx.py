# shared/filters/adx.py
"""
ADX-based trading filter.

Filters trades based on ADX (Average Directional Index) trend strength.
"""

from collections import deque
from typing import cast

from ..config._values import config_value
from ..protocols.bar import BarProtocol
from ..protocols.filter import FilterResult
from .base import BaseFilter
from .registry import register_filter


@register_filter("adx")
class AdxFilter(BaseFilter):
    """
    Filter trades by ADX trend strength.

    Blocks trades when ADX is below the configured threshold, indicating
    weak or ranging market conditions where trend-following strategies
    may underperform.

    Config options:
        enabled: bool - Whether filter is active (default True)
        period: int - Period for ADX calculation (default 14)
        threshold: float - Minimum ADX value to allow trades (default 25.0)
    """

    @property
    def name(self) -> str:
        return "adx"

    def __init__(self, config: dict[str, object]):
        super().__init__(config)
        self.enabled = config_value(config, "enabled", True)
        self.period = config_value(config, "period", 14)
        self.threshold = config_value(config, "threshold", 25.0)

        # State for ADX calculation
        self._prev_close: float | None = None
        self._prev_high: float | None = None
        self._prev_low: float | None = None

        # Smoothed directional movement values
        self._plus_dm_values: deque[float] = deque(maxlen=self.period)
        self._minus_dm_values: deque[float] = deque(maxlen=self.period)
        self._tr_values: deque[float] = deque(maxlen=self.period)

        # Smoothed values for DI calculation
        self._smoothed_plus_dm: float | None = None
        self._smoothed_minus_dm: float | None = None
        self._smoothed_tr: float | None = None

        # ADX calculation state
        self._dx_values: deque[float] = deque(maxlen=self.period)
        self._adx: float | None = None
        self._plus_di: float | None = None
        self._minus_di: float | None = None
        self._ready = False

    def _calculate_true_range(self, high: float, low: float, prev_close: float | None) -> float:
        """
        Calculate True Range for current bar.

        True Range is the maximum of:
        - High - Low
        - |High - Previous Close|
        - |Low - Previous Close|

        Args:
            high: Current bar high
            low: Current bar low
            prev_close: Previous bar close

        Returns:
            True range value
        """
        high_low = high - low

        if prev_close is not None:
            high_close = abs(high - prev_close)
            low_close = abs(low - prev_close)
            return max(high_low, high_close, low_close)
        return high_low

    def _calculate_directional_movement(
        self, high: float, low: float, prev_high: float | None, prev_low: float | None
    ) -> tuple[float, float]:
        """
        Calculate +DM and -DM for current bar.

        +DM = High - Previous High (if positive and > -DM)
        -DM = Previous Low - Low (if positive and > +DM)

        Args:
            high: Current bar high
            low: Current bar low
            prev_high: Previous bar high
            prev_low: Previous bar low

        Returns:
            Tuple of (+DM, -DM)
        """
        if prev_high is None or prev_low is None:
            return 0.0, 0.0

        up_move = high - prev_high
        down_move = prev_low - low

        plus_dm = 0.0
        minus_dm = 0.0

        if up_move > down_move and up_move > 0:
            plus_dm = up_move
        if down_move > up_move and down_move > 0:
            minus_dm = down_move

        return plus_dm, minus_dm

    def update(self, bar: BarProtocol) -> None:
        """
        Update ADX calculation with new bar data.

        Uses Wilder's smoothing method for ADX calculation.

        Args:
            bar: Current bar data
        """
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)

        # Calculate True Range
        tr = self._calculate_true_range(high, low, self._prev_close)
        self._tr_values.append(tr)

        # Calculate Directional Movement
        plus_dm, minus_dm = self._calculate_directional_movement(
            high, low, self._prev_high, self._prev_low
        )
        self._plus_dm_values.append(plus_dm)
        self._minus_dm_values.append(minus_dm)

        # Store previous values for next calculation
        self._prev_close = close
        self._prev_high = high
        self._prev_low = low

        # Need at least period bars to calculate
        if len(self._tr_values) < self.period:
            return

        # Calculate smoothed values using Wilder's smoothing
        if self._smoothed_tr is None:
            # First calculation: SMA (sum / period)
            self._smoothed_tr = sum(self._tr_values) / self.period
            self._smoothed_plus_dm = sum(self._plus_dm_values) / self.period
            self._smoothed_minus_dm = sum(self._minus_dm_values) / self.period
        else:
            # Subsequent calculations: Wilder's smoothing
            self._smoothed_tr = self._smoothed_tr - (self._smoothed_tr / self.period) + tr
            self._smoothed_plus_dm = (
                cast(float, self._smoothed_plus_dm)
                - (cast(float, self._smoothed_plus_dm) / self.period)
                + plus_dm
            )
            self._smoothed_minus_dm = (
                cast(float, self._smoothed_minus_dm)
                - (cast(float, self._smoothed_minus_dm) / self.period)
                + minus_dm
            )

        # Calculate +DI and -DI
        if self._smoothed_tr > 0:
            self._plus_di = (self._smoothed_plus_dm / self._smoothed_tr) * 100
            self._minus_di = (self._smoothed_minus_dm / self._smoothed_tr) * 100
        else:
            self._plus_di = 0.0
            self._minus_di = 0.0

        # Calculate DX
        di_sum = self._plus_di + self._minus_di
        if di_sum > 0:
            dx = abs(self._plus_di - self._minus_di) / di_sum * 100
        else:
            dx = 0.0

        self._dx_values.append(dx)

        # Calculate ADX once we have enough DX values
        if len(self._dx_values) >= self.period:
            if self._adx is None:
                # First ADX: simple average of DX values
                self._adx = sum(self._dx_values) / len(self._dx_values)
            else:
                # Subsequent ADX: Wilder's smoothing
                self._adx = ((self._adx * (self.period - 1)) + dx) / self.period

            self._ready = True

    def check(self, bar: BarProtocol) -> FilterResult:
        """
        Check if current ADX is above threshold.

        Args:
            bar: Current bar data

        Returns:
            FilterResult indicating pass/fail
        """
        if not self.enabled:
            return FilterResult.allow()

        if not self._ready or self._adx is None:
            return FilterResult.block("ADX not yet calculated (warming up)")

        if self._adx < self.threshold:
            return FilterResult.block(
                f"Weak trend: ADX {self._adx:.1f} < threshold {self.threshold}"
            )

        return FilterResult.allow()

    def reset(self) -> None:
        """Reset filter state."""
        self._prev_close = None
        self._prev_high = None
        self._prev_low = None
        self._plus_dm_values.clear()
        self._minus_dm_values.clear()
        self._tr_values.clear()
        self._smoothed_plus_dm = None
        self._smoothed_minus_dm = None
        self._smoothed_tr = None
        self._dx_values.clear()
        self._adx = None
        self._plus_di = None
        self._minus_di = None
        self._ready = False

    def get_adx(self) -> float | None:
        """
        Get current ADX value.

        Returns:
            Current ADX or None if not yet calculated
        """
        return self._adx

    def get_plus_di(self) -> float | None:
        """
        Get current +DI value.

        Returns:
            Current +DI or None if not yet calculated
        """
        return self._plus_di

    def get_minus_di(self) -> float | None:
        """
        Get current -DI value.

        Returns:
            Current -DI or None if not yet calculated
        """
        return self._minus_di
