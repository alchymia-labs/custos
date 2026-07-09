# shared/filters/__init__.py
"""
Trading filters package.

Provides filter registry and implementations for signal filtering.
"""

from .adx import AdxFilter
from .base import BaseFilter
from .cooldown import CooldownFilter
from .momentum import MomentumFilter
from .mtf import MTFFilter
from .regime import RegimeFilter
from .registry import (
    clear_registry,
    create_filter,
    is_filter_registered,
    list_filters,
    register_filter,
)

# Import filter implementations to trigger registration
from .time_filter import TimeFilter, parse_trading_hours
from .volatility import VolatilityFilter
from .volume import VolumeFilter

__all__ = [
    # Base and registry
    "BaseFilter",
    "register_filter",
    "create_filter",
    "list_filters",
    "is_filter_registered",
    "clear_registry",
    # Filter implementations
    "TimeFilter",
    "CooldownFilter",
    "VolatilityFilter",
    "VolumeFilter",
    "RegimeFilter",
    "MomentumFilter",
    "MTFFilter",
    "AdxFilter",
    # Time parsing helper
    "parse_trading_hours",
]
