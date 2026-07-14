# shared/risk/orders.py
"""
Order price calculations.

Calculates stop loss and take profit prices.
"""

from decimal import Decimal

from ..signals.types import SignalDirection


class OrderPriceCalculator:
    """
    Calculate stop loss and take profit prices.

    Supports fixed percentage and ATR-based calculations.
    """

    def __init__(self, config: dict):
        """
        Initialize calculator with trade risk config.

        Args:
            config: Trade risk config dict with keys:
                - stop_loss: StopLossConfig dict
                - take_profit: TakeProfitConfig dict
        """
        self.config = config

    def calculate_stop_loss(
        self,
        entry_price: Decimal,
        direction: SignalDirection,
        atr: Decimal | None = None,
    ) -> Decimal | None:
        """
        Calculate stop loss price.

        Args:
            entry_price: Entry price (Decimal)
            direction: Trade direction
            atr: Current ATR value (Decimal, required for ATR-based stops)

        Returns:
            Stop loss price or None if not configured
        """
        sl_config = self.config.get("stop_loss", {})
        if not sl_config:
            return None

        method = sl_config.get("method", "none")
        if method == "none":
            return None

        is_long = direction in (SignalDirection.ENTER_LONG,)

        if method == "fixed" and sl_config.get("fixed"):
            pct = Decimal(str(sl_config["fixed"].get("value", 0.02)))
            if is_long:
                return entry_price * (1 - pct)
            else:
                return entry_price * (1 + pct)

        elif method == "atr" and sl_config.get("atr") and atr is not None:
            multiplier = Decimal(str(sl_config["atr"].get("multiplier", 2.0)))
            if is_long:
                return entry_price - (atr * multiplier)
            else:
                return entry_price + (atr * multiplier)

        return None

    def calculate_take_profit(
        self,
        entry_price: Decimal,
        direction: SignalDirection,
        atr: Decimal | None = None,
        stop_loss: Decimal | None = None,
    ) -> Decimal | None:
        """
        Calculate take profit price.

        Args:
            entry_price: Entry price (Decimal)
            direction: Trade direction
            atr: Current ATR value (Decimal)
            stop_loss: Stop loss price (Decimal, for risk/reward calculation)

        Returns:
            Take profit price or None if not configured
        """
        tp_config = self.config.get("take_profit", {})
        if not tp_config:
            return None

        method = tp_config.get("method", "none")
        if method == "none":
            return None

        is_long = direction in (SignalDirection.ENTER_LONG,)

        # Fixed percentage
        if method == "fixed" and tp_config.get("fixed"):
            pct = Decimal(str(tp_config["fixed"].get("value", 0.04)))
            if is_long:
                return entry_price * (1 + pct)
            else:
                return entry_price * (1 - pct)

        # ATR-based
        elif method == "atr" and tp_config.get("atr") and atr is not None:
            multiplier = Decimal(str(tp_config["atr"].get("multiplier", 3.0)))
            if is_long:
                return entry_price + (atr * multiplier)
            else:
                return entry_price - (atr * multiplier)

        # Risk/reward ratio
        elif method == "risk_reward" and stop_loss is not None:
            rr_ratio = tp_config.get("risk_reward_ratio")
            if rr_ratio:
                risk = abs(entry_price - stop_loss)
                reward = risk * Decimal(str(rr_ratio))
                if is_long:
                    return entry_price + reward
                else:
                    return entry_price - reward

        return None

    def calculate_trailing_stop(
        self,
        entry_price: Decimal,
        current_price: Decimal,
        current_stop: Decimal,
        direction: SignalDirection,
    ) -> Decimal | None:
        """
        Calculate updated trailing stop price.

        Args:
            entry_price: Original entry price (Decimal)
            current_price: Current market price (Decimal)
            current_stop: Current stop loss price (Decimal)
            direction: Trade direction

        Returns:
            New stop price or None if trailing not activated
        """
        sl_config = self.config.get("stop_loss", {})
        trailing = sl_config.get("trailing")
        if not trailing or not trailing.get("enabled"):
            return None

        activation_pct = Decimal(str(trailing.get("activation_pct", 0.02)))
        trailing_pct = Decimal(str(trailing.get("trailing_pct", 0.01)))

        is_long = direction in (SignalDirection.ENTER_LONG,)

        if is_long:
            profit_pct = (current_price - entry_price) / entry_price
            if profit_pct >= activation_pct:
                new_stop = current_price * (1 - trailing_pct)
                return max(current_stop, new_stop)  # Only move up
        else:
            profit_pct = (entry_price - current_price) / entry_price
            if profit_pct >= activation_pct:
                new_stop = current_price * (1 + trailing_pct)
                return min(current_stop, new_stop)  # Only move down

        return None
