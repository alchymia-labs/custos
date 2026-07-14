# shared/filters/volume.py
"""
Volume-based trading filter.

Filters trades based on volume relative to moving average.
"""

from ..protocols.bar import BarProtocol
from ..protocols.filter import FilterResult
from .base import BaseFilter
from .registry import register_filter


@register_filter("volume")
class VolumeFilter(BaseFilter):
    """
    Filter trades based on volume relative to moving average.

    Only allows trading when current volume exceeds a threshold
    multiplied by the average volume (EMA or SMA).

    Config options:
        enabled: bool - Whether filter is active (default True)
        ma_period: int - Period for volume moving average (default 20)
        threshold: float - Multiplier for average volume (default 1.0)
        ma_type: str - Moving average type: "ema" or "sma" (default "ema")
    """

    @property
    def name(self) -> str:
        return "volume"

    def __init__(self, config: dict):
        super().__init__(config)
        self.enabled = config.get("enabled", True)
        self._ma_period = config.get("ma_period", 20)
        self._threshold = config.get("threshold", 1.0)
        self._ma_type = config.get("ma_type", "ema").lower()

        # Validate ma_type
        if self._ma_type not in ("ema", "sma"):
            raise ValueError(f"Invalid ma_type: {self._ma_type}. Must be 'ema' or 'sma'")

        # State for moving average calculation
        self._volume_ma: float | None = None
        self._bar_count: int = 0

        # For SMA: store recent volumes
        self._volume_buffer: list[float] = []

        self._ready = False

    def update(self, bar: BarProtocol) -> None:
        """Update volume moving average with new bar data."""
        volume = float(bar.volume)
        self._bar_count += 1

        if self._ma_type == "ema":
            self._update_ema(volume)
        else:
            self._update_sma(volume)

        # Ready after ma_period bars
        if self._bar_count >= self._ma_period:
            self._ready = True

    def _update_ema(self, volume: float) -> None:
        """Update exponential moving average."""
        if self._volume_ma is None:
            self._volume_ma = volume
        else:
            alpha = 2.0 / (self._ma_period + 1)
            self._volume_ma = alpha * volume + (1 - alpha) * self._volume_ma

    def _update_sma(self, volume: float) -> None:
        """Update simple moving average."""
        self._volume_buffer.append(volume)

        # Keep only the last ma_period values
        if len(self._volume_buffer) > self._ma_period:
            self._volume_buffer.pop(0)

        # Calculate SMA
        self._volume_ma = sum(self._volume_buffer) / len(self._volume_buffer)

    def check(self, bar: BarProtocol) -> FilterResult:
        """Check if current volume meets the threshold."""
        if not self.enabled:
            return FilterResult.allow()

        if not self._ready or self._volume_ma is None:
            return FilterResult.block("Volume filter not ready (warming up)")

        current_volume = float(bar.volume)
        required_volume = self._volume_ma * self._threshold

        if current_volume >= required_volume:
            # Calculate size factor based on how much volume exceeds threshold
            # Cap at 2.0 to avoid extreme position sizing
            size_factor = min(current_volume / required_volume, 2.0)
            return FilterResult.allow(size_factor=size_factor)
        else:
            ratio = current_volume / self._volume_ma if self._volume_ma > 0 else 0
            return FilterResult.block(
                f"Volume {current_volume:.0f} below threshold "
                f"({ratio:.2f}x avg, need {self._threshold:.2f}x)"
            )

    def reset(self) -> None:
        """Reset filter state."""
        self._volume_ma = None
        self._bar_count = 0
        self._volume_buffer = []
        self._ready = False

    @property
    def current_ma(self) -> float | None:
        """Get current moving average value (for debugging/logging)."""
        return self._volume_ma

    @property
    def bar_count(self) -> int:
        """Get number of bars processed (for debugging/logging)."""
        return self._bar_count
