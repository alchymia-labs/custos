# shared/filters/base.py
"""
Base filter class.

Provides abstract base class for all filter implementations.
"""

from abc import ABC, abstractmethod

from ..protocols.bar import BarProtocol
from ..protocols.filter import FilterResult


class BaseFilter(ABC):
    """
    Abstract base class for filters.

    Subclasses must implement name, update(), check(), and is_ready().
    """

    def __init__(self, config: dict[str, object]):
        """
        Initialize filter with configuration.

        Args:
            config: Filter configuration dictionary
        """
        self.config = config
        self._ready = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Filter name for logging and registry."""
        ...

    @abstractmethod
    def update(self, bar: BarProtocol) -> None:
        """Update filter state with new bar data."""
        ...

    @abstractmethod
    def check(self, bar: BarProtocol) -> FilterResult:
        """Evaluate filter condition."""
        ...

    def is_ready(self) -> bool:
        """Check if filter has enough data."""
        return self._ready
