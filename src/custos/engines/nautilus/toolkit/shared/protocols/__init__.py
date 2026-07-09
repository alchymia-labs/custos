# shared/protocols/__init__.py
"""
Protocol definitions for platform abstraction.

These protocols define interfaces that platform-specific types must satisfy,
enabling shared modules to work with both NautilusTrader and Hummingbot.
"""

from .bar import BarProtocol
from .filter import FilterProtocol, FilterResult

__all__ = [
    "BarProtocol",
    "FilterProtocol",
    "FilterResult",
]
