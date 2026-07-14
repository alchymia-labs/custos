"""
Risk management utilities.

Provides platform-agnostic risk calculations for stop loss, take profit,
and trailing stop functionality.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from ..config._values import config_value
from ..signals.types import SignalDirection


@dataclass
class TrailingStopConfig:
    """
    Trailing stop configuration.

    Attributes:
        enabled: Whether trailing stop is enabled
        activation_pct: Profit percentage to activate trailing (e.g., 0.02 = 2%)
        trailing_pct: Trailing distance as percentage (e.g., 0.01 = 1%)
    """

    enabled: bool = False
    activation_pct: Decimal | float = Decimal("0.02")
    trailing_pct: Decimal | float = Decimal("0.01")

    def __post_init__(self) -> None:
        """Convert types."""
        if isinstance(self.activation_pct, (int, float)):
            self.activation_pct = Decimal(str(self.activation_pct))
        if isinstance(self.trailing_pct, (int, float)):
            self.trailing_pct = Decimal(str(self.trailing_pct))

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "TrailingStopConfig":
        """Create config from dictionary."""
        return cls(
            enabled=config_value(data, "enabled", False),
            activation_pct=config_value(data, "activation_pct", 0.02),
            trailing_pct=config_value(data, "trailing_pct", 0.01),
        )


@dataclass
class RiskConfig:
    """
    Risk management configuration.

    Attributes:
        stop_loss_atr_multiplier: ATR multiplier for stop loss distance
        take_profit_atr_multiplier: ATR multiplier for take profit distance
        stop_loss_pct: Fixed percentage stop loss (alternative to ATR-based)
        take_profit_pct: Fixed percentage take profit (alternative to ATR-based)
        trailing_stop: Trailing stop configuration
        max_loss_per_trade_pct: Maximum loss per trade as percentage of balance
    """

    stop_loss_atr_multiplier: Decimal | float = Decimal("2.0")
    take_profit_atr_multiplier: Decimal | float = Decimal("4.0")
    stop_loss_pct: Decimal | float | None = None
    take_profit_pct: Decimal | float | None = None
    trailing_stop: TrailingStopConfig | None = None
    max_loss_per_trade_pct: Decimal | float = Decimal("0.02")  # 2% max loss

    def __post_init__(self) -> None:
        """Convert types."""
        if isinstance(self.stop_loss_atr_multiplier, (int, float)):
            self.stop_loss_atr_multiplier = Decimal(str(self.stop_loss_atr_multiplier))
        if isinstance(self.take_profit_atr_multiplier, (int, float)):
            self.take_profit_atr_multiplier = Decimal(str(self.take_profit_atr_multiplier))
        if self.stop_loss_pct is not None and isinstance(self.stop_loss_pct, (int, float)):
            self.stop_loss_pct = Decimal(str(self.stop_loss_pct))
        if self.take_profit_pct is not None and isinstance(self.take_profit_pct, (int, float)):
            self.take_profit_pct = Decimal(str(self.take_profit_pct))
        if isinstance(self.max_loss_per_trade_pct, (int, float)):
            self.max_loss_per_trade_pct = Decimal(str(self.max_loss_per_trade_pct))

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "RiskConfig":
        """Create config from dictionary."""
        trailing_data = cast(dict[str, object] | None, data.get("trailing_stop"))
        trailing = TrailingStopConfig.from_dict(trailing_data) if trailing_data else None

        return cls(
            stop_loss_atr_multiplier=config_value(data, "stop_loss_atr_multiplier", 2.0),
            take_profit_atr_multiplier=config_value(data, "take_profit_atr_multiplier", 4.0),
            stop_loss_pct=cast(Decimal | float | None, data.get("stop_loss_pct")),
            take_profit_pct=cast(Decimal | float | None, data.get("take_profit_pct")),
            trailing_stop=trailing,
            max_loss_per_trade_pct=config_value(data, "max_loss_per_trade_pct", 0.02),
        )


class RiskManager:
    """
    Platform-agnostic risk management calculations.

    Calculates stop loss, take profit, and trailing stop levels
    based on ATR or percentage configurations.
    """

    def __init__(self, config: RiskConfig | dict[str, object]) -> None:
        """
        Initialize risk manager.

        Args:
            config: Risk configuration (RiskConfig or dict)
        """
        if isinstance(config, dict):
            config = RiskConfig.from_dict(config)
        self.config = config

    def get_stop_loss(
        self,
        entry_price: Decimal | float,
        atr: Decimal | float,
        direction: SignalDirection,
    ) -> Decimal:
        """
        Calculate stop loss price.

        Args:
            entry_price: Entry price
            atr: Current ATR value
            direction: Trade direction (LONG or SHORT)

        Returns:
            Stop loss price
        """
        entry = self._to_decimal(entry_price)
        atr_value = self._to_decimal(atr)

        # Calculate distance
        if self.config.stop_loss_pct is not None:
            distance = entry * Decimal(str(self.config.stop_loss_pct))
        else:
            distance = atr_value * Decimal(str(self.config.stop_loss_atr_multiplier))

        # Apply direction
        if direction in (SignalDirection.ENTER_LONG, SignalDirection.EXIT_SHORT):
            return entry - distance
        elif direction in (SignalDirection.ENTER_SHORT, SignalDirection.EXIT_LONG):
            return entry + distance
        else:
            return entry

    def get_take_profit(
        self,
        entry_price: Decimal | float,
        atr: Decimal | float,
        direction: SignalDirection,
    ) -> Decimal:
        """
        Calculate take profit price.

        Args:
            entry_price: Entry price
            atr: Current ATR value
            direction: Trade direction (LONG or SHORT)

        Returns:
            Take profit price
        """
        entry = self._to_decimal(entry_price)
        atr_value = self._to_decimal(atr)

        # Calculate distance
        if self.config.take_profit_pct is not None:
            distance = entry * Decimal(str(self.config.take_profit_pct))
        else:
            distance = atr_value * Decimal(str(self.config.take_profit_atr_multiplier))

        # Apply direction
        if direction in (SignalDirection.ENTER_LONG, SignalDirection.EXIT_SHORT):
            return entry + distance
        elif direction in (SignalDirection.ENTER_SHORT, SignalDirection.EXIT_LONG):
            return entry - distance
        else:
            return entry

    def update_trailing_stop(
        self,
        entry_price: Decimal | float,
        current_price: Decimal | float,
        current_stop: Decimal | float,
        direction: SignalDirection,
    ) -> Decimal:
        """
        Update trailing stop level based on current price.

        Args:
            entry_price: Original entry price
            current_price: Current market price
            current_stop: Current stop loss level
            direction: Trade direction (LONG or SHORT)

        Returns:
            Updated stop loss price (may be same as current if not triggered)
        """
        if not self.config.trailing_stop or not self.config.trailing_stop.enabled:
            return self._to_decimal(current_stop)

        entry = self._to_decimal(entry_price)
        current = self._to_decimal(current_price)
        stop = self._to_decimal(current_stop)

        trailing = self.config.trailing_stop
        activation_pct = trailing.activation_pct
        trailing_pct = trailing.trailing_pct

        if direction == SignalDirection.ENTER_LONG:
            # Check if trailing is activated (price moved up by activation_pct)
            profit_pct = (current - entry) / entry
            if profit_pct >= activation_pct:
                # Calculate new trailing stop
                new_stop = current * (Decimal(1) - Decimal(str(trailing_pct)))
                # Only move stop up, never down
                return max(stop, new_stop)

        elif direction == SignalDirection.ENTER_SHORT:
            # Check if trailing is activated (price moved down by activation_pct)
            profit_pct = (entry - current) / entry
            if profit_pct >= activation_pct:
                # Calculate new trailing stop
                new_stop = current * (Decimal(1) + Decimal(str(trailing_pct)))
                # Only move stop down, never up
                return min(stop, new_stop)

        return stop

    def should_stop_out(
        self,
        current_price: Decimal | float,
        stop_loss: Decimal | float,
        direction: SignalDirection,
    ) -> bool:
        """
        Check if position should be stopped out.

        Args:
            current_price: Current market price
            stop_loss: Stop loss level
            direction: Trade direction

        Returns:
            True if stop loss is triggered
        """
        current = self._to_decimal(current_price)
        stop = self._to_decimal(stop_loss)

        if direction == SignalDirection.ENTER_LONG:
            return current <= stop
        elif direction == SignalDirection.ENTER_SHORT:
            return current >= stop
        return False

    def should_take_profit(
        self,
        current_price: Decimal | float,
        take_profit: Decimal | float,
        direction: SignalDirection,
    ) -> bool:
        """
        Check if take profit should be triggered.

        Args:
            current_price: Current market price
            take_profit: Take profit level
            direction: Trade direction

        Returns:
            True if take profit is triggered
        """
        current = self._to_decimal(current_price)
        tp = self._to_decimal(take_profit)

        if direction == SignalDirection.ENTER_LONG:
            return current >= tp
        elif direction == SignalDirection.ENTER_SHORT:
            return current <= tp
        return False

    def should_move_to_break_even(
        self,
        entry_price: Decimal | float,
        current_price: Decimal | float,
        is_long: bool,
        trigger_pct: Decimal | float,
    ) -> bool:
        """
        Check if stop loss should move to break-even.

        Args:
            entry_price: Position entry price
            current_price: Current market price
            is_long: True for long position, False for short
            trigger_pct: Profit threshold as decimal fraction (0.015 = 1.5%),
                same unit as config activation_pct and update_trailing_stop (CR-4)

        Returns:
            True if position has reached break-even trigger
        """
        entry = self._to_decimal(entry_price)
        current = self._to_decimal(current_price)
        trigger = self._to_decimal(trigger_pct)

        if entry <= 0:
            return False

        if is_long:
            profit_pct = (current - entry) / entry
        else:
            profit_pct = (entry - current) / entry

        return profit_pct >= trigger

    def calculate_risk_reward(
        self,
        entry_price: Decimal | float,
        stop_loss: Decimal | float,
        take_profit: Decimal | float,
    ) -> Decimal:
        """
        Calculate risk/reward ratio.

        Args:
            entry_price: Entry price
            stop_loss: Stop loss level
            take_profit: Take profit level

        Returns:
            Risk/reward ratio
        """
        entry = self._to_decimal(entry_price)
        stop = self._to_decimal(stop_loss)
        tp = self._to_decimal(take_profit)

        risk = abs(entry - stop)
        reward = abs(tp - entry)

        if risk == 0:
            return Decimal("0")

        return reward / risk

    @staticmethod
    def _to_decimal(value: Decimal | float | int) -> Decimal:
        """Convert value to Decimal."""
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
