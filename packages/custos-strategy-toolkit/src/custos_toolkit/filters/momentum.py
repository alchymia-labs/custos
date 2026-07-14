# shared/filters/momentum.py
"""
Momentum-based trading filter.

Filters trades based on momentum indicators: RSI, MACD, or ROC.
"""

from collections import deque
from dataclasses import dataclass
from typing import Literal

from ..protocols.bar import BarProtocol
from ..protocols.filter import FilterResult
from .base import BaseFilter
from .registry import register_filter


@dataclass
class RSIConfig:
    """RSI indicator configuration."""

    period: int = 14
    long_min: float = 30.0  # Min RSI for long entry
    long_max: float = 70.0  # Max RSI for long entry


@dataclass
class MACDConfig:
    """MACD indicator configuration."""

    fast: int = 12
    slow: int = 26
    signal: int = 9
    histogram_positive: bool = True  # Require histogram > 0 for long


@dataclass
class ROCConfig:
    """Rate of Change indicator configuration."""

    period: int = 12
    long_threshold: float = 0.0  # Min ROC % for long entry


@register_filter("momentum")
class MomentumFilter(BaseFilter):
    """
    Filter trades based on momentum indicators.

    Supports RSI, MACD, and ROC indicators. Each indicator can be used
    to filter long entries based on configured thresholds.

    Config options:
        enabled: bool - Whether filter is active (default True)
        indicator: str - Which indicator to use: "rsi", "macd", or "roc" (default "rsi")

        RSI config:
            rsi_period: int - RSI period (default 14)
            rsi_long_min: float - Min RSI for long entry (default 30)
            rsi_long_max: float - Max RSI for long entry (default 70)

        MACD config:
            macd_fast: int - Fast EMA period (default 12)
            macd_slow: int - Slow EMA period (default 26)
            macd_signal: int - Signal line period (default 9)
            macd_histogram_positive: bool - Require positive histogram (default True)

        ROC config:
            roc_period: int - ROC lookback period (default 12)
            roc_long_threshold: float - Min ROC % for long entry (default 0)
    """

    @property
    def name(self) -> str:
        return "momentum"

    def __init__(self, config: dict):
        super().__init__(config)
        self.enabled = config.get("enabled", True)
        self.indicator: Literal["rsi", "macd", "roc"] = config.get("indicator", "rsi")

        # Validate indicator
        valid_indicators = ("rsi", "macd", "roc")
        if self.indicator not in valid_indicators:
            raise ValueError(
                f"Invalid indicator '{self.indicator}'. Must be one of: {valid_indicators}"
            )

        # RSI configuration
        self.rsi_config = RSIConfig(
            period=config.get("rsi_period", 14),
            long_min=config.get("rsi_long_min", 30.0),
            long_max=config.get("rsi_long_max", 70.0),
        )

        # MACD configuration
        self.macd_config = MACDConfig(
            fast=config.get("macd_fast", 12),
            slow=config.get("macd_slow", 26),
            signal=config.get("macd_signal", 9),
            histogram_positive=config.get("macd_histogram_positive", True),
        )

        # ROC configuration
        self.roc_config = ROCConfig(
            period=config.get("roc_period", 12),
            long_threshold=config.get("roc_long_threshold", 0.0),
        )

        # Price history for calculations
        self._prices: deque[float] = deque(maxlen=self._required_bars())

        # MACD EMA state
        self._macd_fast_ema: float | None = None
        self._macd_slow_ema: float | None = None
        self._macd_signal_ema: float | None = None
        self._macd_update_count: int = 0

        self._ready = False

    def _required_bars(self) -> int:
        """Calculate minimum bars needed for the selected indicator."""
        if self.indicator == "rsi":
            return self.rsi_config.period + 1
        elif self.indicator == "macd":
            # Need slow period for EMA, plus signal period for signal line
            return self.macd_config.slow + self.macd_config.signal
        elif self.indicator == "roc":
            return self.roc_config.period + 1
        return 1

    def update(self, bar: BarProtocol) -> None:
        """
        Update filter state with new bar data.

        Appends close price to history and updates EMA calculations for MACD.
        """
        price = bar.close
        self._prices.append(price)

        # Update MACD EMAs if using MACD indicator
        if self.indicator == "macd":
            self._update_macd_emas(price)

        # Check if ready
        self._check_ready()

    def _update_macd_emas(self, price: float) -> None:
        """Update MACD exponential moving averages."""
        self._macd_update_count += 1

        # Fast EMA
        fast_mult = 2.0 / (self.macd_config.fast + 1)
        if self._macd_fast_ema is None:
            self._macd_fast_ema = price
        else:
            self._macd_fast_ema = price * fast_mult + self._macd_fast_ema * (1 - fast_mult)

        # Slow EMA
        slow_mult = 2.0 / (self.macd_config.slow + 1)
        if self._macd_slow_ema is None:
            self._macd_slow_ema = price
        else:
            self._macd_slow_ema = price * slow_mult + self._macd_slow_ema * (1 - slow_mult)

        # Signal EMA (of MACD line)
        if self._macd_update_count >= self.macd_config.slow:
            macd_line = self._macd_fast_ema - self._macd_slow_ema
            signal_mult = 2.0 / (self.macd_config.signal + 1)
            if self._macd_signal_ema is None:
                self._macd_signal_ema = macd_line
            else:
                self._macd_signal_ema = macd_line * signal_mult + self._macd_signal_ema * (
                    1 - signal_mult
                )

    def _check_ready(self) -> None:
        """Check if filter has enough data to operate."""
        if self.indicator == "rsi":
            self._ready = len(self._prices) >= self.rsi_config.period + 1
        elif self.indicator == "macd":
            self._ready = self._macd_update_count >= self.macd_config.slow + self.macd_config.signal
        elif self.indicator == "roc":
            self._ready = len(self._prices) >= self.roc_config.period + 1

    def check(self, bar: BarProtocol) -> FilterResult:
        """
        Check if momentum conditions allow trading.

        Args:
            bar: Current bar data

        Returns:
            FilterResult indicating pass/fail based on momentum indicator
        """
        if not self.enabled:
            return FilterResult.allow()

        if not self._ready:
            required = self._required_bars()
            current = len(self._prices)
            return FilterResult.block(f"Insufficient data ({current}/{required} bars)")

        if self.indicator == "rsi":
            return self._check_rsi()
        elif self.indicator == "macd":
            return self._check_macd()
        elif self.indicator == "roc":
            return self._check_roc()

        return FilterResult.allow()

    def _check_rsi(self) -> FilterResult:
        """Check RSI conditions for long entry."""
        rsi = self._calculate_rsi()

        if rsi is None:
            return FilterResult.block("RSI calculation failed")

        if rsi < self.rsi_config.long_min:
            return FilterResult.block(f"RSI {rsi:.1f} below minimum {self.rsi_config.long_min}")

        if rsi > self.rsi_config.long_max:
            return FilterResult.block(f"RSI {rsi:.1f} above maximum {self.rsi_config.long_max}")

        return FilterResult.allow()

    def _calculate_rsi(self) -> float | None:
        """
        Calculate RSI value from price history.

        Returns:
            RSI value (0-100) or None if insufficient data
        """
        prices = list(self._prices)
        if len(prices) < self.rsi_config.period + 1:
            return None

        gains = []
        losses = []
        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        # Use last N periods
        avg_gain = sum(gains[-self.rsi_config.period :]) / self.rsi_config.period
        avg_loss = sum(losses[-self.rsi_config.period :]) / self.rsi_config.period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _check_macd(self) -> FilterResult:
        """Check MACD conditions for long entry."""
        if self._macd_fast_ema is None or self._macd_slow_ema is None:
            return FilterResult.block("MACD not initialized")

        macd_line = self._macd_fast_ema - self._macd_slow_ema

        if self.macd_config.histogram_positive:
            if self._macd_signal_ema is None:
                return FilterResult.block("MACD signal line not initialized")

            histogram = macd_line - self._macd_signal_ema
            if histogram <= 0:
                return FilterResult.block(f"MACD histogram {histogram:.4f} is not positive")

        return FilterResult.allow()

    def _check_roc(self) -> FilterResult:
        """Check ROC conditions for long entry."""
        roc = self._calculate_roc()

        if roc is None:
            return FilterResult.block("ROC calculation failed")

        if roc < self.roc_config.long_threshold:
            return FilterResult.block(
                f"ROC {roc:.2f}% below threshold {self.roc_config.long_threshold}%"
            )

        return FilterResult.allow()

    def _calculate_roc(self) -> float | None:
        """
        Calculate Rate of Change from price history.

        Returns:
            ROC percentage or None if insufficient data
        """
        prices = list(self._prices)
        if len(prices) < self.roc_config.period + 1:
            return None

        current_price = prices[-1]
        past_price = prices[-self.roc_config.period - 1]

        if past_price > 0:
            return ((current_price - past_price) / past_price) * 100
        return None

    # Public accessor methods for diagnostics

    def get_rsi(self) -> float | None:
        """
        Get current RSI value.

        Returns:
            RSI value (0-100) or None if not calculable
        """
        if not self._ready or self.indicator != "rsi":
            return None
        return self._calculate_rsi()

    def get_macd(self) -> dict | None:
        """
        Get current MACD values.

        Returns:
            Dict with macd_line, signal_line, histogram or None
        """
        if not self._ready or self.indicator != "macd":
            return None

        if self._macd_fast_ema is None or self._macd_slow_ema is None:
            return None

        macd_line = self._macd_fast_ema - self._macd_slow_ema

        result = {"macd_line": macd_line}

        if self._macd_signal_ema is not None:
            result["signal_line"] = self._macd_signal_ema
            result["histogram"] = macd_line - self._macd_signal_ema

        return result

    def get_roc(self) -> float | None:
        """
        Get current Rate of Change value.

        Returns:
            ROC percentage or None if not calculable
        """
        if not self._ready or self.indicator != "roc":
            return None
        return self._calculate_roc()
