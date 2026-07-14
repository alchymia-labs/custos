# shared/protocols/bar.py
"""
Bar/candle data protocol.

Defines the interface that platform-specific bar types must satisfy.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class BarProtocol(Protocol):
    """
    Abstract bar/candle data.

    Both NautilusTrader Bar and Hummingbot candle data
    should satisfy this protocol.
    """

    @property
    def open(self) -> float:
        """Opening price."""
        ...

    @property
    def high(self) -> float:
        """High price."""
        ...

    @property
    def low(self) -> float:
        """Low price."""
        ...

    @property
    def close(self) -> float:
        """Closing price."""
        ...

    @property
    def volume(self) -> float:
        """Volume."""
        ...

    @property
    def timestamp(self) -> int:
        """Unix timestamp in nanoseconds."""
        ...
