# shared/position/sizer.py
"""
Position sizing calculations.

Provides position size calculation with Kelly, scaling, and dynamic adjustments.
"""

from decimal import ROUND_DOWN, Decimal
from typing import Any


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Get value from dict or object attribute."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class PositionSizer:
    """
    Calculate position sizes based on configuration.

    Supports:
    - Percentage of capital
    - Fixed size
    - Kelly criterion
    - Scaling (pyramid, fixed, martingale)
    """

    def __init__(self, config: dict | Any):
        """
        Initialize sizer with configuration.

        Args:
            config: Position configuration dict or struct with keys:
                - size_type: "percentage", "fixed", or "kelly"
                - size_value: Base size value
                - kelly: KellyConfig dict or struct
                - scaling: ScalingConfig dict or struct
        """
        self.size_type = _get(config, "size_type", "percentage")
        self.size_value = Decimal(str(_get(config, "size_value", 0.1)))
        self.kelly_config = _get(config, "kelly", {})
        self.scaling_config = _get(config, "scaling", {})

    def calculate_base_size(self, effective_capital: Decimal) -> Decimal:
        """
        Calculate base position size before adjustments.

        Args:
            effective_capital: Available capital for sizing (Decimal)

        Returns:
            Base position size
        """
        if self.size_type == "percentage":
            return effective_capital * self.size_value
        elif self.size_type == "fixed":
            return self.size_value
        elif self.size_type == "kelly":
            kelly_pct = self._calculate_kelly_percentage()
            return effective_capital * kelly_pct
        else:
            # Unknown type, use percentage as fallback
            return effective_capital * self.size_value

    def apply_signal_strength(self, size: Decimal, strength: Decimal) -> Decimal:
        """
        Adjust size by signal strength.

        Args:
            size: Base size (Decimal)
            strength: Signal strength 0.0 to 1.0 (Decimal)

        Returns:
            Adjusted size
        """
        return size * strength

    def apply_scaling(self, size: Decimal, entry_count: int) -> Decimal:
        """
        Apply scaling adjustment based on entry count.

        Args:
            size: Base size
            entry_count: Current number of entries (0 = first entry)

        Returns:
            Scaled size (0 if max entries reached)
        """
        scaling = self.scaling_config
        if not scaling or not _get(scaling, "enabled", False):
            return size

        max_entries = _get(scaling, "max_entries", 3)
        if entry_count >= max_entries:
            return Decimal("0")

        method = _get(scaling, "method", "pyramid")

        if method == "pyramid":
            pyramid_config = _get(scaling, "pyramid", {})
            factor = _get(pyramid_config, "scale_factor", 0.5)
            return size * Decimal(str(factor**entry_count))

        elif method == "fixed":
            # Fixed scaling returns same size each time
            fixed_config = _get(scaling, "fixed", {})
            fixed_pct = _get(fixed_config, "size_per_entry", 0.1)
            return Decimal(str(fixed_pct))

        elif method == "martingale":
            martingale_config = _get(scaling, "martingale", {})
            multiplier = _get(martingale_config, "multiplier", 2.0)
            return size * Decimal(str(multiplier**entry_count))

        return size

    def _calculate_kelly_percentage(self) -> Decimal:
        """
        Calculate Kelly criterion percentage.

        Kelly % = W - [(1-W) / R]
        Where W = win_rate, R = payoff_ratio

        Returns:
            Kelly percentage (clamped to >= 0)
        """
        if not self.kelly_config:
            return self.size_value

        w = _get(self.kelly_config, "win_rate", 0.5)
        r = _get(self.kelly_config, "payoff_ratio", 2.0)
        fraction = _get(self.kelly_config, "fraction", 0.25)

        if r <= 0:
            return Decimal("0")

        kelly_pct = w - ((1 - w) / r)
        kelly_pct = max(0, kelly_pct) * fraction

        return Decimal(str(kelly_pct))

    def check_limits(
        self,
        size: Decimal,
        effective_capital: Decimal,
        limits: dict | Any | None = None,
    ) -> Decimal:
        """
        Apply position limits (min/max).

        Args:
            size: Calculated size (Decimal)
            effective_capital: Current capital (Decimal)
            limits: Limits config dict or struct with keys:
                - max_position_pct: Maximum position as percentage of capital
                - max_trade_size: Absolute maximum trade size (exchange limit)
                - min_order_size: Minimum order size

        Returns:
            Size clamped to limits, rounded down to avoid precision issues
        """
        if not limits:
            # Round down to 3 decimals to avoid precision issues exceeding limits
            return size.quantize(Decimal("0.001"), rounding=ROUND_DOWN)

        # Check max position percentage
        max_pct = _get(limits, "max_position_pct")
        if max_pct:
            max_size = effective_capital * Decimal(str(max_pct))
            size = min(size, max_size)

        # Check absolute max trade size (exchange limit)
        max_trade = _get(limits, "max_trade_size")
        if max_trade:
            size = min(size, Decimal(str(max_trade)))

        # Check min order size
        min_size = _get(limits, "min_order_size")
        if min_size and size < Decimal(str(min_size)):
            return Decimal("0")  # Too small, return 0

        # Round down to 3 decimals to avoid precision issues exceeding limits
        return size.quantize(Decimal("0.001"), rounding=ROUND_DOWN)
