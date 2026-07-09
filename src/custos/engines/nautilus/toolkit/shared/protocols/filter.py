# shared/protocols/filter.py
"""
Filter protocol and result types.

Defines the interface for trading filters that can be used
across different trading platforms.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .bar import BarProtocol


@dataclass
class FilterResult:
    """
    Result of filter evaluation.

    Attributes:
        passed: Whether the filter condition passed
        size_factor: Optional multiplier for position size (default 1.0)
        reason: Description of why filter failed (for logging)
    """

    passed: bool
    size_factor: float = 1.0
    reason: str = ""

    @classmethod
    def allow(cls, size_factor: float = 1.0) -> "FilterResult":
        """Create a passing result."""
        return cls(passed=True, size_factor=size_factor)

    @classmethod
    def block(cls, reason: str) -> "FilterResult":
        """Create a blocking result with reason."""
        return cls(passed=False, reason=reason)


@runtime_checkable
class FilterProtocol(Protocol):
    """
    Abstract filter interface.

    Filters evaluate market conditions and decide whether
    to allow or block trading signals.
    """

    @property
    def name(self) -> str:
        """Filter name for logging and registry."""
        ...

    def update(self, bar: BarProtocol) -> None:
        """
        Update filter state with new bar data.

        Called on every bar to maintain filter state
        (e.g., moving averages, ATR calculations).
        """
        ...

    def check(self, bar: BarProtocol) -> FilterResult:
        """
        Evaluate filter condition.

        Args:
            bar: Current bar data

        Returns:
            FilterResult indicating pass/fail and optional size factor
        """
        ...

    def is_ready(self) -> bool:
        """
        Check if filter has enough data to operate.

        Returns False during warmup period.
        """
        ...
