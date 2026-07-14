"""
Trading configuration models (msgspec.Struct for NautilusTrader).

Provides type-safe configuration classes using msgspec.Struct with frozen=True
for compatibility with NautilusTrader's StrategyConfig.
"""

from typing import cast

import msgspec

from ._input import section, value
from .allocation import AllocationConfig, build_allocation_config


class FeeConfig(msgspec.Struct, frozen=True):
    """Trading fee configuration."""

    maker: float = 0.0002
    taker: float = 0.0004
    funding_rate: float = 0.0


class SplitOrdersConfig(msgspec.Struct, frozen=True):
    """Split orders configuration for large order execution."""

    enabled: bool = False
    max_single_order_pct: float = 0.1
    interval_ms: int = 1000


class PriceImprovementConfig(msgspec.Struct, frozen=True):
    """Price improvement configuration for better entry."""

    enabled: bool = False
    wait_for_pullback: bool = False
    pullback_pct: float = 0.002
    pullback_timeout: int = 300


class ExecutionConfig(msgspec.Struct, frozen=True):
    """Order execution configuration."""

    price_type: str = "mid"
    limit_order_timeout: int = 60
    slippage_tolerance: float = 0.001
    retry_on_failure: bool = True
    max_retries: int = 3
    split_orders: SplitOrdersConfig = SplitOrdersConfig()
    price_improvement: PriceImprovementConfig = PriceImprovementConfig()


class TradingConfig(msgspec.Struct, frozen=True):
    """Trading configuration."""

    connector: str = "binance_perpetual"
    leverage: int = 1
    pairs: tuple[str, ...] = ("BTC-USDT",)
    direction: str = "both"
    order_type: str = "limit"
    position_mode: str = "ONEWAY"
    fees: FeeConfig = FeeConfig()
    execution: ExecutionConfig = ExecutionConfig()
    allocation: AllocationConfig | None = None
    raw: dict[str, object] | None = None

    @property
    def enable_long(self) -> bool:
        return self.direction in ("long", "both")

    @property
    def enable_short(self) -> bool:
        return self.direction in ("short", "both")


def build_trading_config(
    trading_dict: dict[str, object],
    raw_dict: dict[str, object] | None = None,
) -> TradingConfig:
    """Build TradingConfig from YAML dict."""
    if not trading_dict:
        return TradingConfig()

    execution_data = section(trading_dict, "execution")
    if execution_data:
        split_orders_data = section(execution_data, "split_orders")
        split_orders = (
            SplitOrdersConfig(
                enabled=value(split_orders_data, "enabled", False),
                max_single_order_pct=value(split_orders_data, "max_single_order_pct", 0.1),
                interval_ms=value(split_orders_data, "interval_ms", 1000),
            )
            if split_orders_data
            else SplitOrdersConfig()
        )

        price_improvement_data = section(execution_data, "price_improvement")
        price_improvement = (
            PriceImprovementConfig(
                enabled=value(price_improvement_data, "enabled", False),
                wait_for_pullback=value(price_improvement_data, "wait_for_pullback", False),
                pullback_pct=value(price_improvement_data, "pullback_pct", 0.002),
                pullback_timeout=value(price_improvement_data, "pullback_timeout", 300),
            )
            if price_improvement_data
            else PriceImprovementConfig()
        )

        execution = ExecutionConfig(
            price_type=value(execution_data, "price_type", "mid"),
            limit_order_timeout=value(execution_data, "limit_order_timeout", 60),
            slippage_tolerance=value(execution_data, "slippage_tolerance", 0.001),
            retry_on_failure=value(execution_data, "retry_on_failure", True),
            max_retries=value(execution_data, "max_retries", 3),
            split_orders=split_orders,
            price_improvement=price_improvement,
        )
    else:
        execution = ExecutionConfig()

    # Convert list to tuple for pairs
    raw_pairs: list[str] | tuple[str, ...] = value(trading_dict, "pairs", ["BTC-USDT"])
    pairs = tuple(raw_pairs) if isinstance(raw_pairs, list) else raw_pairs

    # Build fees config
    fees_data = section(trading_dict, "fees")
    if fees_data:
        fees = FeeConfig(
            maker=value(fees_data, "maker", 0.0002),
            taker=value(fees_data, "taker", 0.0004),
            funding_rate=value(fees_data, "funding_rate", 0.0),
        )
    else:
        # Backward compatibility: support old single fee field
        old_fee = value(trading_dict, "fee", 0.0004)
        fees = FeeConfig(maker=old_fee, taker=old_fee, funding_rate=0.0)

    # Build allocation config if provided
    allocation_data = cast(dict[str, object] | None, value(trading_dict, "allocation"))
    allocation = build_allocation_config(allocation_data) if allocation_data else None

    return TradingConfig(
        connector=value(trading_dict, "connector", "binance_perpetual"),
        leverage=value(trading_dict, "leverage", 1),
        pairs=pairs,
        direction=value(trading_dict, "direction", "both"),
        order_type=value(trading_dict, "order_type", "limit"),
        position_mode=value(trading_dict, "position_mode", "ONEWAY"),
        fees=fees,
        execution=execution,
        allocation=allocation,
        raw=raw_dict,
    )
