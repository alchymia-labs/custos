"""
Signal types for strategy communication.

Provides platform-agnostic signal definitions that can be used
by both Hummingbot and NautilusTrader strategies.

OKX Signal Bot Compatibility:
    This module supports OKX Signal Bot Alert Specification 2.0 Section B.
    See: https://www.okx.com/zh-hans/help/signal-bot-alert-message-specifications
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class InvestmentType(Enum):
    """OKX investment type for position sizing."""

    MARGIN = "margin"  # Fixed margin in quote currency (entry only)
    CONTRACT = "contract"  # Fixed number of contracts (entry only)
    PERCENTAGE_BALANCE = "percentage_balance"  # % of available balance (entry only)
    PERCENTAGE_INVESTMENT = "percentage_investment"  # % of active investment (entry only)
    PERCENTAGE_POSITION = "percentage_position"  # % of open position (exit only)


class OrderType(Enum):
    """Order type for signal execution."""

    MARKET = "market"
    LIMIT = "limit"


class SignalDirection(Enum):
    """Trading signal direction."""

    ENTER_LONG = "enter_long"
    ENTER_SHORT = "enter_short"
    NEUTRAL = "neutral"
    EXIT_LONG = "exit_long"
    EXIT_SHORT = "exit_short"

    def is_entry(self) -> bool:
        """Check if this is an entry signal."""
        return self in (SignalDirection.ENTER_LONG, SignalDirection.ENTER_SHORT)

    def is_exit(self) -> bool:
        """Check if this is an exit signal."""
        return self in (SignalDirection.EXIT_LONG, SignalDirection.EXIT_SHORT)

    def opposite(self) -> "SignalDirection":
        """Get the opposite direction."""
        opposites = {
            SignalDirection.ENTER_LONG: SignalDirection.ENTER_SHORT,
            SignalDirection.ENTER_SHORT: SignalDirection.ENTER_LONG,
            SignalDirection.EXIT_LONG: SignalDirection.EXIT_SHORT,
            SignalDirection.EXIT_SHORT: SignalDirection.EXIT_LONG,
        }
        return opposites.get(self, SignalDirection.NEUTRAL)


@dataclass
class Signal:
    """
    Trading signal with direction, price, and metadata.

    Core Attributes:
        direction: The signal direction (ENTER_LONG, ENTER_SHORT, NEUTRAL, EXIT_LONG, EXIT_SHORT)
        price: Current price when signal was generated
        strength: Signal strength from 0.0 to 1.0 (optional, default 1.0)
        timestamp: Unix timestamp in nanoseconds when signal was generated (optional)
        pair: Trading pair symbol (e.g., "BTC-USDT")
        metadata: Additional signal metadata (e.g., indicator values)

    OKX Compatible Fields (all optional, will use config defaults if None):
        investment_type: How to interpret the amount (margin/contract/percentage_*)
        amount: Position size value (interpretation depends on investment_type)
        order_type: Order execution type (market/limit)
        order_price_offset: Limit order price offset percentage (0-100)
        max_lag: Maximum acceptable signal delay in seconds (1-3600)
        signal_token: OKX signal authentication token
    """

    # === Core fields ===
    direction: SignalDirection
    price: Decimal = Decimal("0")
    strength: float = 1.0
    timestamp: int | None = None
    pair: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

    # === OKX compatible fields (all optional) ===
    investment_type: str | None = None
    amount: Decimal | None = None
    order_type: str | None = None
    order_price_offset: Decimal | None = None
    max_lag: int | None = None
    signal_token: str | None = None

    def __post_init__(self) -> None:
        """Validate and normalize signal data."""
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError(f"Signal strength must be between 0 and 1, got {self.strength}")
        if isinstance(self.price, (int, float)):
            self.price = Decimal(str(self.price))
        # Normalize amount to Decimal if provided
        if self.amount is not None and isinstance(self.amount, (int, float)):
            self.amount = Decimal(str(self.amount))
        # Normalize order_price_offset to Decimal if provided
        if self.order_price_offset is not None and isinstance(
            self.order_price_offset, (int, float)
        ):
            self.order_price_offset = Decimal(str(self.order_price_offset))

    def is_actionable(self) -> bool:
        """Check if signal requires action (not neutral)."""
        return self.direction != SignalDirection.NEUTRAL

    def is_enter_long(self) -> bool:
        """Check if this is a long entry signal."""
        return self.direction == SignalDirection.ENTER_LONG

    def is_enter_short(self) -> bool:
        """Check if this is a short entry signal."""
        return self.direction == SignalDirection.ENTER_SHORT

    def is_exit(self) -> bool:
        """Check if this is an exit signal."""
        return self.direction.is_exit()

    @classmethod
    def neutral(cls, price: Decimal | float = 0, pair: str = "", **metadata: object) -> "Signal":
        """Create a neutral (no action) signal with optional metadata."""
        return cls(
            direction=SignalDirection.NEUTRAL,
            price=Decimal(str(price)) if isinstance(price, (int, float)) else price,
            pair=pair,
            metadata=metadata,
        )

    @classmethod
    def enter_long(
        cls,
        price: Decimal | float,
        pair: str = "",
        strength: float = 1.0,
        amount: Decimal | float | None = None,
        investment_type: str | None = None,
        order_type: str | None = None,
        order_price_offset: Decimal | float | None = None,
        **metadata: object,
    ) -> "Signal":
        """Create a long entry signal with optional OKX fields."""
        return cls(
            direction=SignalDirection.ENTER_LONG,
            price=Decimal(str(price)) if isinstance(price, (int, float)) else price,
            pair=pair,
            strength=strength,
            amount=Decimal(str(amount))
            if amount is not None and isinstance(amount, (int, float))
            else amount,
            investment_type=investment_type,
            order_type=order_type,
            order_price_offset=(
                Decimal(str(order_price_offset))
                if order_price_offset is not None and isinstance(order_price_offset, (int, float))
                else order_price_offset
            ),
            metadata=metadata,
        )

    @classmethod
    def enter_short(
        cls,
        price: Decimal | float,
        pair: str = "",
        strength: float = 1.0,
        amount: Decimal | float | None = None,
        investment_type: str | None = None,
        order_type: str | None = None,
        order_price_offset: Decimal | float | None = None,
        **metadata: object,
    ) -> "Signal":
        """Create a short entry signal with optional OKX fields."""
        return cls(
            direction=SignalDirection.ENTER_SHORT,
            price=Decimal(str(price)) if isinstance(price, (int, float)) else price,
            pair=pair,
            strength=strength,
            amount=Decimal(str(amount))
            if amount is not None and isinstance(amount, (int, float))
            else amount,
            investment_type=investment_type,
            order_type=order_type,
            order_price_offset=(
                Decimal(str(order_price_offset))
                if order_price_offset is not None and isinstance(order_price_offset, (int, float))
                else order_price_offset
            ),
            metadata=metadata,
        )

    @classmethod
    def exit_long(
        cls,
        price: Decimal | float,
        pair: str = "",
        amount: Decimal | float | None = None,
        investment_type: str | None = None,
        order_type: str | None = None,
        order_price_offset: Decimal | float | None = None,
        **metadata: object,
    ) -> "Signal":
        """Create a long exit signal with optional OKX fields."""
        return cls(
            direction=SignalDirection.EXIT_LONG,
            price=Decimal(str(price)) if isinstance(price, (int, float)) else price,
            pair=pair,
            amount=Decimal(str(amount))
            if amount is not None and isinstance(amount, (int, float))
            else amount,
            investment_type=investment_type,
            order_type=order_type,
            order_price_offset=(
                Decimal(str(order_price_offset))
                if order_price_offset is not None and isinstance(order_price_offset, (int, float))
                else order_price_offset
            ),
            metadata=metadata,
        )

    @classmethod
    def exit_short(
        cls,
        price: Decimal | float,
        pair: str = "",
        amount: Decimal | float | None = None,
        investment_type: str | None = None,
        order_type: str | None = None,
        order_price_offset: Decimal | float | None = None,
        **metadata: object,
    ) -> "Signal":
        """Create a short exit signal with optional OKX fields."""
        return cls(
            direction=SignalDirection.EXIT_SHORT,
            price=Decimal(str(price)) if isinstance(price, (int, float)) else price,
            pair=pair,
            amount=Decimal(str(amount))
            if amount is not None and isinstance(amount, (int, float))
            else amount,
            investment_type=investment_type,
            order_type=order_type,
            order_price_offset=(
                Decimal(str(order_price_offset))
                if order_price_offset is not None and isinstance(order_price_offset, (int, float))
                else order_price_offset
            ),
            metadata=metadata,
        )

    def has_okx_fields(self) -> bool:
        """Check if signal has any OKX-specific fields set."""
        return any(
            [
                self.investment_type is not None,
                self.amount is not None,
                self.order_type is not None,
                self.order_price_offset is not None,
                self.max_lag is not None,
                self.signal_token is not None,
            ]
        )
