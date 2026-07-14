"""
SuperTrend Strategy - NautilusTrader Implementation

ATR-based trend following strategy using dynamic support/resistance lines.

Usage:
    # Sandbox (testnet) trading - from command line
    python main.py --strategy supertrend --mode sandbox

    # Live trading - from command line
    python main.py --strategy supertrend --mode live
"""

from custos_toolkit_nautilus.adapter.indicators import SuperTrend

from .strategy import SuperTrendStrategy, SuperTrendStrategyConfig

__all__ = [
    # Strategy
    "SuperTrend",
    "SuperTrendStrategy",
    "SuperTrendStrategyConfig",
]
