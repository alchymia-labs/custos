"""
Trading configuration models (msgspec.Struct for NautilusTrader).

Provides type-safe configuration classes using msgspec.Struct with frozen=True
for compatibility with NautilusTrader's StrategyConfig.
"""

import msgspec

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
    raw: dict | None = None

    @property
    def enable_long(self) -> bool:
        return self.direction in ("long", "both")

    @property
    def enable_short(self) -> bool:
        return self.direction in ("short", "both")


def build_trading_config(trading_dict: dict, raw_dict: dict | None = None) -> TradingConfig:
    """Build TradingConfig from YAML dict."""
    if not trading_dict:
        return TradingConfig()

    execution_data = trading_dict.get("execution", {})
    if execution_data:
        split_orders_data = execution_data.get("split_orders", {})
        split_orders = (
            SplitOrdersConfig(**split_orders_data) if split_orders_data else SplitOrdersConfig()
        )

        price_improvement_data = execution_data.get("price_improvement", {})
        price_improvement = (
            PriceImprovementConfig(**price_improvement_data)
            if price_improvement_data
            else PriceImprovementConfig()
        )

        execution = ExecutionConfig(
            price_type=execution_data.get("price_type", "mid"),
            limit_order_timeout=execution_data.get("limit_order_timeout", 60),
            slippage_tolerance=execution_data.get("slippage_tolerance", 0.001),
            retry_on_failure=execution_data.get("retry_on_failure", True),
            max_retries=execution_data.get("max_retries", 3),
            split_orders=split_orders,
            price_improvement=price_improvement,
        )
    else:
        execution = ExecutionConfig()

    # Convert list to tuple for pairs
    pairs = trading_dict.get("pairs", ["BTC-USDT"])
    if isinstance(pairs, list):
        pairs = tuple(pairs)

    # Build fees config
    fees_data = trading_dict.get("fees", {})
    if fees_data:
        fees = FeeConfig(
            maker=fees_data.get("maker", 0.0002),
            taker=fees_data.get("taker", 0.0004),
            funding_rate=fees_data.get("funding_rate", 0.0),
        )
    else:
        # Backward compatibility: support old single fee field
        old_fee = trading_dict.get("fee", 0.0004)
        fees = FeeConfig(maker=old_fee, taker=old_fee, funding_rate=0.0)

    # Build allocation config if provided
    allocation_data = trading_dict.get("allocation")
    allocation = build_allocation_config(allocation_data) if allocation_data else None

    return TradingConfig(
        connector=trading_dict.get("connector", "binance_perpetual"),
        leverage=trading_dict.get("leverage", 1),
        pairs=pairs,
        direction=trading_dict.get("direction", "both"),
        order_type=trading_dict.get("order_type", "limit"),
        position_mode=trading_dict.get("position_mode", "ONEWAY"),
        fees=fees,
        execution=execution,
        allocation=allocation,
        raw=raw_dict,
    )
