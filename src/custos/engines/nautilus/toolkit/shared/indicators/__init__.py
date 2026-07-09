"""
Technical indicators for strategy development.

This module provides lightweight, streaming indicator implementations
for use in strategy development.

For batch calculations on DataFrames, use pandas-ta directly:
  import pandas_ta as ta
  ta.supertrend(high, low, close, length, multiplier)
  ta.adx(high, low, close, length)
  ta.atr(high, low, close, length)

For NautilusTrader strategies, use the platform-specific wrappers in:
  shared/nautilus/indicators/  (e.g. SuperTrend)
"""

__all__: list[str] = []
