# shared/filters/mtf.py
"""
Multi-TimeFrame (MTF) filter.

Filters trades based on alignment with higher timeframe direction.
The filter tracks a direction value that can be set externally by the strategy
which subscribes to higher timeframe bars.
"""

from ..protocols.bar import BarProtocol
from ..protocols.filter import FilterResult
from ..signals.types import Signal, SignalDirection
from .base import BaseFilter
from .registry import register_filter


@register_filter("mtf")
class MTFFilter(BaseFilter):
    """
    Filter trades based on higher timeframe direction alignment.

    This filter doesn't subscribe to higher timeframe bars itself (that's platform-specific).
    Instead, the strategy subscribes to HTF bars and calls set_direction() to update the
    filter's state. The check() method then validates signal alignment with the stored direction.

    Config options:
        enabled: bool - Whether filter is active (default True)
        alignment_mode: str - "same_direction" or "not_against" (default "same_direction")
            - same_direction: Signal must match HTF direction exactly
            - not_against: Signal can proceed if HTF is neutral (0)
        higher_timeframe: str - Reference timeframe (default "1h"), for documentation only
    """

    @property
    def name(self) -> str:
        return "mtf"

    def __init__(self, config: dict):
        super().__init__(config)
        self.enabled = config.get("enabled", True)
        self.alignment_mode = config.get("alignment_mode", "same_direction")
        self.higher_timeframe = config.get("higher_timeframe", "1h")

        # Validate alignment_mode
        valid_modes = ("same_direction", "not_against")
        if self.alignment_mode not in valid_modes:
            raise ValueError(
                f"Invalid alignment_mode '{self.alignment_mode}'. Must be one of: {valid_modes}"
            )

        # Direction state: 1=bullish, -1=bearish, 0=neutral, None=unknown
        self._direction: int | None = None
        self._ready = False

        # HTF bar type for automatic detection
        self._htf_bar_type = None

    def set_direction(self, direction: int) -> None:
        """
        Set the higher timeframe direction.

        Called by the strategy when it receives a higher timeframe bar update.

        Args:
            direction: 1 for bullish, -1 for bearish, 0 for neutral
        """
        if direction not in (1, -1, 0):
            raise ValueError(f"Direction must be 1, -1, or 0, got {direction}")
        self._direction = direction
        self._ready = True

    def get_direction(self) -> int | None:
        """
        Get the current higher timeframe direction.

        Returns:
            1 for bullish, -1 for bearish, 0 for neutral, None if not set
        """
        return self._direction

    def set_htf_bar_type(self, bar_type) -> None:
        """
        Set the higher timeframe bar type for identification.

        When set, update() will automatically detect HTF bars and
        calculate direction from them.

        Args:
            bar_type: The Nautilus BarType for higher timeframe
        """
        self._htf_bar_type = bar_type

    def is_htf_bar(self, bar) -> bool:
        """
        Check if bar is from higher timeframe.

        Returns True if bar matches the HTF bar type.
        """
        if self._htf_bar_type is None:
            return False
        return hasattr(bar, "bar_type") and bar.bar_type == self._htf_bar_type

    def update(self, bar: BarProtocol) -> None:
        """
        Update filter state with new bar data.

        If HTF bar type is set and bar matches, automatically calculate
        direction from the bar's open/close. Otherwise, direction is
        updated externally via set_direction().
        """
        if not self.is_htf_bar(bar):
            return  # Only process HTF bars

        # Calculate direction from bar
        close = float(bar.close)
        open_ = float(bar.open)

        if close > open_:
            self._direction = 1  # Bullish
        elif close < open_:
            self._direction = -1  # Bearish
        else:
            self._direction = 0  # Neutral

        self._ready = True

    def check(self, bar: BarProtocol, signal: Signal | None = None) -> FilterResult:
        """
        Check if signal aligns with higher timeframe direction.

        Args:
            bar: Current bar data (not used directly)
            signal: Trading signal to validate (optional for backward compatibility)

        Returns:
            FilterResult indicating pass/fail based on alignment
        """
        if not self.enabled:
            return FilterResult.allow()

        if not self._ready or self._direction is None:
            return FilterResult.block("MTF direction not set")

        # If no signal provided, just check if direction is non-zero
        if signal is None:
            if self._direction != 0:
                return FilterResult.allow()
            else:
                if self.alignment_mode == "same_direction":
                    return FilterResult.block("MTF direction is neutral")
                else:  # not_against mode
                    return FilterResult.allow(size_factor=0.5)

        # Validate signal alignment with HTF direction
        signal_direction = signal.direction

        # For ENTER_LONG: HTF should be bullish (1) or neutral (0) in not_against mode
        if signal_direction == SignalDirection.ENTER_LONG:
            if self._direction == 1:
                return FilterResult.allow()
            elif self._direction == 0 and self.alignment_mode == "not_against":
                return FilterResult.allow(size_factor=0.5)
            else:
                return FilterResult.block(
                    f"Long signal blocked: HTF direction is {self._direction_str()}"
                )

        # For ENTER_SHORT: HTF should be bearish (-1) or neutral (0) in not_against mode
        elif signal_direction == SignalDirection.ENTER_SHORT:
            if self._direction == -1:
                return FilterResult.allow()
            elif self._direction == 0 and self.alignment_mode == "not_against":
                return FilterResult.allow(size_factor=0.5)
            else:
                return FilterResult.block(
                    f"Short signal blocked: HTF direction is {self._direction_str()}"
                )

        # For exit signals and neutral, always allow
        elif signal_direction in (
            SignalDirection.EXIT_LONG,
            SignalDirection.EXIT_SHORT,
            SignalDirection.NEUTRAL,
        ):
            return FilterResult.allow()

        return FilterResult.allow()

    def _direction_str(self) -> str:
        """Get human-readable direction string."""
        if self._direction == 1:
            return "bullish"
        elif self._direction == -1:
            return "bearish"
        elif self._direction == 0:
            return "neutral"
        return "unknown"

    def reset(self) -> None:
        """Reset the filter state."""
        self._direction = None
        self._ready = False
        self._htf_bar_type = None
