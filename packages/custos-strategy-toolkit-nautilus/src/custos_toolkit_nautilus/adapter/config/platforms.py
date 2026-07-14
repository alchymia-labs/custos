"""
Platform configuration models (msgspec.Struct for NautilusTrader).

Provides type-safe configuration classes using msgspec.Struct with frozen=True
for compatibility with NautilusTrader's StrategyConfig.
"""

from typing import TypedDict, cast

import msgspec
from custos_toolkit.config import extract_value

from ._input import section, value


class _HummingbotKwargs(TypedDict, total=False):
    candles_exchange: str | None
    candles_pair: str | None
    candles_interval: str


class _TradingNodeKwargs(TypedDict, total=False):
    timeout_connection: float
    timeout_reconciliation: float
    timeout_portfolio: float
    timeout_disconnection: float
    reconciliation_lookback_mins: int
    database: "DatabaseConfig"


class DatabaseConfig(msgspec.Struct, frozen=True):
    """
    Database configuration for Redis persistence.

    Used by NautilusTrader for cache and message bus persistence,
    and by Snapshot feature for indicator state persistence.
    """

    enabled: bool = False
    type: str = "redis"
    host: str = "localhost"
    port: int = 6379
    username: str | None = None
    password: str | None = None


class HummingbotPlatformConfig(msgspec.Struct, frozen=True):
    """Hummingbot platform configuration."""

    candles_exchange: str | None = None
    candles_pair: str | None = None
    candles_interval: str = "1h"


class TradingNodeConfig(msgspec.Struct, frozen=True):
    """NautilusTrader TradingNode configuration."""

    timeout_connection: float = 30.0
    timeout_reconciliation: float = 10.0
    timeout_portfolio: float = 10.0
    timeout_disconnection: float = 10.0
    reconciliation_lookback_mins: int = 1440
    database: DatabaseConfig = DatabaseConfig()


class NautilusPlatformConfig(msgspec.Struct, frozen=True):
    """NautilusTrader platform configuration."""

    venue: str = "BINANCE"
    bar_type: str = "1-HOUR"
    bar_aggregation: str = "EXTERNAL"  # EXTERNAL (exchange bars) or INTERNAL (from ticks)
    trading_node: TradingNodeConfig = TradingNodeConfig()


class PlatformsConfig(msgspec.Struct, frozen=True):
    """Platform configurations."""

    hummingbot: HummingbotPlatformConfig = HummingbotPlatformConfig()
    nautilus: NautilusPlatformConfig = NautilusPlatformConfig()
    raw: dict[str, object] | None = None


def build_platforms_config(
    platforms_dict: dict[str, object],
    raw_dict: dict[str, object] | None = None,
) -> PlatformsConfig:
    """Build PlatformsConfig from YAML dict."""
    if not platforms_dict:
        return PlatformsConfig()

    raw_hb_data = section(platforms_dict, "hummingbot")
    # Filter out None values for msgspec compatibility
    hb_data = cast(
        _HummingbotKwargs,
        {k: v for k, v in raw_hb_data.items() if v is not None},
    )
    hummingbot = HummingbotPlatformConfig(**hb_data) if hb_data else HummingbotPlatformConfig()

    nautilus_data = section(platforms_dict, "nautilus")
    if nautilus_data:
        # Build trading_node config
        trading_node_data = section(nautilus_data, "trading_node")

        # Build database config
        db_data = section(trading_node_data, "database")
        database = (
            DatabaseConfig(
                enabled=value(db_data, "enabled", False),
                type=value(db_data, "type", "redis"),
                host=value(db_data, "host", "localhost"),
                port=value(db_data, "port", 6379),
                username=cast(str | None, value(db_data, "username")),
                password=cast(str | None, value(db_data, "password")),
            )
            if db_data
            else DatabaseConfig()
        )

        # Filter out Redis config keys for TradingNodeConfig constructor
        # (these are handled separately - database is now in DatabaseConfig)
        redis_keys = {"database", "cache", "message_bus"}
        trading_node_kwargs = cast(
            _TradingNodeKwargs,
            {k: v for k, v in trading_node_data.items() if k not in redis_keys},
        )
        trading_node_kwargs["database"] = database

        trading_node = (
            TradingNodeConfig(**trading_node_kwargs) if trading_node_kwargs else TradingNodeConfig()
        )

        nautilus = NautilusPlatformConfig(
            venue=cast(str, extract_value(value(nautilus_data, "venue"), "BINANCE")),
            bar_type=cast(str, extract_value(value(nautilus_data, "bar_type"), "1-HOUR")),
            bar_aggregation=cast(
                str, extract_value(value(nautilus_data, "bar_aggregation"), "EXTERNAL")
            ),
            trading_node=trading_node,
        )
    else:
        nautilus = NautilusPlatformConfig()

    return PlatformsConfig(hummingbot=hummingbot, nautilus=nautilus, raw=raw_dict)
