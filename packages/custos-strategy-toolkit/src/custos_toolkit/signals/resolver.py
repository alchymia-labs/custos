"""
Signal resolver for field completion and format conversion.

Provides layered resolution of signal fields (signal > config > defaults)
and bidirectional format conversion (internal Signal <-> OKX format).
"""

import time
from datetime import UTC
from decimal import Decimal
from typing import Any

from custos_toolkit.signals.types import Signal, SignalDirection

# Default values when neither signal nor config provides a value
_DEFAULTS = {
    "investment_type": "percentage_investment",
    "order_type": "market",
    "order_price_offset": Decimal("0.1"),
    "max_lag": 60,
}


class SignalResolver:
    """
    Signal field resolver with layered priority.

    Resolution priority:
    1. Signal field has value -> use it
    2. Config value -> use it
    3. System default -> use it

    Responsibilities:
    1. Complete missing signal fields using config defaults
    2. Convert between internal Signal and OKX JSON format
    """

    def __init__(self, signal_config=None, position_config=None):
        """
        Initialize resolver with configuration.

        Args:
            signal_config: SignalConfig from base_config (optional)
            position_config: PositionConfig for size_type mapping (optional)
        """
        self._signal_config = signal_config
        self._position_config = position_config

    def resolve(self, signal: Signal) -> Signal:
        """
        Complete missing signal fields using config defaults.

        Args:
            signal: Input signal (may have missing fields)

        Returns:
            New Signal with all fields populated
        """
        return Signal(
            # Core fields (pass through)
            direction=signal.direction,
            price=signal.price,
            strength=signal.strength,
            timestamp=signal.timestamp or self._current_timestamp_ns(),
            pair=signal.pair,
            metadata=signal.metadata,
            # OKX fields (layered resolution)
            investment_type=self._resolve_investment_type(signal),
            amount=self._resolve_amount(signal),
            order_type=self._resolve_order_type(signal),
            order_price_offset=self._resolve_order_price_offset(signal),
            max_lag=self._resolve_max_lag(signal),
            signal_token=self._resolve_signal_token(signal),
        )

    def from_external(self, external_signal: Any) -> Signal:
        """
        Convert external signal to internal Signal type.

        Handles multiple input formats:
        - Signal: Pass through (already internal type)
        - dict: Parse as OKX JSON format

        Args:
            external_signal: External signal in various formats

        Returns:
            Internal Signal object

        Raises:
            ValueError: If signal type is not recognized
        """
        if isinstance(external_signal, Signal):
            return external_signal

        if isinstance(external_signal, dict):
            return self.from_okx_format(external_signal)

        raise ValueError(f"Unknown signal type: {type(external_signal)}")

    def _resolve_investment_type(self, signal: Signal) -> str:
        """Resolve investment_type: signal > config > position mapping > default."""
        if signal.investment_type:
            return signal.investment_type

        # Try config defaults
        if self._signal_config and self._signal_config.defaults.investment_type:
            return self._signal_config.defaults.investment_type

        # Map from position.size_type
        if self._position_config and self._position_config.size_type:
            mapping = {
                "percentage": "percentage_investment",
                "fixed": "margin",
                "kelly": "percentage_investment",
            }
            return mapping.get(self._position_config.size_type, _DEFAULTS["investment_type"])

        return _DEFAULTS["investment_type"]

    def _resolve_amount(self, signal: Signal) -> Decimal | None:
        """Resolve amount: signal > position.size_value."""
        if signal.amount is not None:
            return signal.amount

        # Use position.size_value if available
        if self._position_config and self._position_config.size_value is not None:
            return Decimal(str(self._position_config.size_value))

        return None

    def _resolve_order_type(self, signal: Signal) -> str:
        """Resolve order_type: signal > config > default."""
        if signal.order_type:
            return signal.order_type

        if self._signal_config and self._signal_config.defaults.order_type:
            return self._signal_config.defaults.order_type

        return _DEFAULTS["order_type"]

    def _resolve_order_price_offset(self, signal: Signal) -> Decimal:
        """Resolve order_price_offset: signal > config > default."""
        if signal.order_price_offset is not None:
            return signal.order_price_offset

        if self._signal_config:
            return Decimal(str(self._signal_config.defaults.order_price_offset))

        return _DEFAULTS["order_price_offset"]

    def _resolve_max_lag(self, signal: Signal) -> int:
        """Resolve max_lag: signal > config > default."""
        if signal.max_lag is not None:
            return signal.max_lag

        if self._signal_config and self._signal_config.okx.max_lag:
            return self._signal_config.okx.max_lag

        return _DEFAULTS["max_lag"]

    def _resolve_signal_token(self, signal: Signal) -> str | None:
        """Resolve signal_token: signal > config."""
        if signal.signal_token:
            return signal.signal_token

        if self._signal_config and self._signal_config.okx.signal_token:
            return self._signal_config.okx.signal_token

        return None

    def _current_timestamp_ns(self) -> int:
        """Get current timestamp in nanoseconds."""
        return int(time.time() * 1_000_000_000)

    # =========================================================================
    # FORMAT CONVERSION
    # =========================================================================

    def to_okx_format(self, signal: Signal) -> dict[str, Any]:
        """
        Convert Signal to OKX B-section JSON format.

        Args:
            signal: Internal Signal object

        Returns:
            Dictionary in OKX signal bot format
        """
        resolved = self.resolve(signal)

        # Convert direction to OKX action
        action = self._direction_to_okx_action(resolved.direction)
        if action is None:
            raise ValueError(f"Cannot convert direction {resolved.direction} to OKX action")

        # Convert pair to instrument
        instrument = self._pair_to_instrument(resolved.pair)

        # Format timestamp (ISO 8601 UTC)
        timestamp_str = self._format_timestamp(resolved.timestamp)

        result = {
            "action": action,
            "instrument": instrument,
            "timestamp": timestamp_str,
            "maxLag": str(resolved.max_lag),
            "investmentType": resolved.investment_type,
            "amount": str(resolved.amount) if resolved.amount is not None else None,
        }

        # Add optional fields
        if resolved.signal_token:
            result["signalToken"] = resolved.signal_token

        if resolved.order_type:
            result["orderType"] = resolved.order_type

        if resolved.order_price_offset is not None and resolved.order_type == "limit":
            result["orderPriceOffset"] = str(resolved.order_price_offset)

        return result

    def from_okx_format(self, data: dict[str, Any]) -> Signal:
        """
        Parse OKX format to internal Signal.

        Args:
            data: Dictionary in OKX signal bot format

        Returns:
            Internal Signal object
        """
        # Required field: action
        action = data.get("action")
        if not action:
            raise ValueError("Missing required field: action")

        direction = self._okx_action_to_direction(action)

        # Parse optional fields
        instrument = data.get("instrument", "")
        pair = self._instrument_to_pair(instrument)

        timestamp = self._parse_timestamp(data.get("timestamp"))

        amount = None
        if data.get("amount"):
            amount = Decimal(str(data["amount"]))

        order_price_offset = None
        if data.get("orderPriceOffset"):
            order_price_offset = Decimal(str(data["orderPriceOffset"]))

        max_lag = None
        if data.get("maxLag"):
            max_lag = int(data["maxLag"])

        return Signal(
            direction=direction,
            pair=pair,
            timestamp=timestamp,
            investment_type=data.get("investmentType"),
            amount=amount,
            order_type=data.get("orderType"),
            order_price_offset=order_price_offset,
            max_lag=max_lag,
            signal_token=data.get("signalToken"),
        )

    def _direction_to_okx_action(self, direction: SignalDirection) -> str | None:
        """Map internal direction to OKX action string."""
        mapping = {
            SignalDirection.ENTER_LONG: "ENTER_LONG",
            SignalDirection.ENTER_SHORT: "ENTER_SHORT",
            SignalDirection.EXIT_LONG: "EXIT_LONG",
            SignalDirection.EXIT_SHORT: "EXIT_SHORT",
        }
        return mapping.get(direction)

    def _okx_action_to_direction(self, action: str) -> SignalDirection:
        """Map OKX action string to internal direction."""
        mapping = {
            "ENTER_LONG": SignalDirection.ENTER_LONG,
            "ENTER_SHORT": SignalDirection.ENTER_SHORT,
            "EXIT_LONG": SignalDirection.EXIT_LONG,
            "EXIT_SHORT": SignalDirection.EXIT_SHORT,
            # Also support lowercase
            "enter_long": SignalDirection.ENTER_LONG,
            "enter_short": SignalDirection.ENTER_SHORT,
            "exit_long": SignalDirection.EXIT_LONG,
            "exit_short": SignalDirection.EXIT_SHORT,
        }
        result = mapping.get(action)
        if result is None:
            raise ValueError(f"Unknown OKX action: {action}")
        return result

    def _pair_to_instrument(self, pair: str) -> str:
        """
        Convert internal pair format to OKX instrument format.

        Internal: BTC-USDT
        OKX: BTC-USDT-SWAP (perpetual) or BTC-USDT (spot)

        Uses instrument_format from config:
        - "okx": BTC-USDT-SWAP
        - "tradingview": BTCUSDT.P
        """
        if not pair:
            return ""

        instrument_format = "okx"
        if self._signal_config:
            instrument_format = self._signal_config.okx.instrument_format

        if instrument_format == "tradingview":
            # BTC-USDT -> BTCUSDT.P
            return pair.replace("-", "") + ".P"
        else:
            # Default OKX format: BTC-USDT -> BTC-USDT-SWAP
            return f"{pair}-SWAP"

    def _instrument_to_pair(self, instrument: str) -> str:
        """
        Convert OKX instrument format to internal pair format.

        OKX: BTC-USDT-SWAP -> BTC-USDT
        TradingView: BTCUSDT.P -> BTC-USDT (requires symbol lookup)
        """
        if not instrument:
            return ""

        # Handle TradingView format
        if instrument.endswith(".P"):
            # BTCUSDT.P -> BTCUSDT -> need to split intelligently
            # This is a simplification; real implementation might need symbol database
            base = instrument[:-2]  # Remove .P
            # Try common quote currencies
            for quote in ["USDT", "USDC", "USD", "BTC", "ETH"]:
                if base.endswith(quote):
                    base_currency = base[: -len(quote)]
                    return f"{base_currency}-{quote}"
            return base

        # Handle OKX format: BTC-USDT-SWAP -> BTC-USDT
        if instrument.endswith("-SWAP"):
            return instrument[:-5]

        return instrument

    def _format_timestamp(self, timestamp_ns: int | None) -> str:
        """Format timestamp to ISO 8601 UTC string."""
        if timestamp_ns is None:
            timestamp_ns = self._current_timestamp_ns()

        # Convert nanoseconds to seconds
        timestamp_s = timestamp_ns / 1_000_000_000
        from datetime import datetime

        dt = datetime.fromtimestamp(timestamp_s, tz=UTC)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _parse_timestamp(self, timestamp_str: str | None) -> int | None:
        """Parse ISO 8601 timestamp to nanoseconds."""
        if not timestamp_str:
            return None

        from datetime import datetime

        # Handle various ISO 8601 formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(timestamp_str.replace("Z", ""), fmt.replace("Z", ""))
                dt = dt.replace(tzinfo=UTC)
                return int(dt.timestamp() * 1_000_000_000)
            except ValueError:
                continue

        return None
