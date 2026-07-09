"""
Platform configuration models (msgspec.Struct for NautilusTrader).

Provides type-safe configuration classes using msgspec.Struct with frozen=True
for compatibility with NautilusTrader's StrategyConfig.
"""

import msgspec

from shared.config import extract_value


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
    raw: dict | None = None


def build_platforms_config(platforms_dict: dict, raw_dict: dict | None = None) -> PlatformsConfig:
    """Build PlatformsConfig from YAML dict."""
    if not platforms_dict:
        return PlatformsConfig()

    hb_data = platforms_dict.get("hummingbot", {})
    # Filter out None values for msgspec compatibility
    hb_data = {k: v for k, v in hb_data.items() if v is not None}
    hummingbot = HummingbotPlatformConfig(**hb_data) if hb_data else HummingbotPlatformConfig()

    nautilus_data = platforms_dict.get("nautilus", {})
    if nautilus_data:
        # Build trading_node config
        trading_node_data = nautilus_data.get("trading_node", {})

        # Build database config
        db_data = trading_node_data.get("database", {})
        database = (
            DatabaseConfig(
                enabled=db_data.get("enabled", False),
                type=db_data.get("type", "redis"),
                host=db_data.get("host", "localhost"),
                port=db_data.get("port", 6379),
                username=db_data.get("username"),
                password=db_data.get("password"),
            )
            if db_data
            else DatabaseConfig()
        )

        # Filter out Redis config keys for TradingNodeConfig constructor
        # (these are handled separately - database is now in DatabaseConfig)
        redis_keys = {"database", "cache", "message_bus"}
        trading_node_kwargs = {k: v for k, v in trading_node_data.items() if k not in redis_keys}
        trading_node_kwargs["database"] = database

        trading_node = (
            TradingNodeConfig(**trading_node_kwargs) if trading_node_kwargs else TradingNodeConfig()
        )

        nautilus = NautilusPlatformConfig(
            venue=extract_value(nautilus_data.get("venue"), "BINANCE"),
            bar_type=extract_value(nautilus_data.get("bar_type"), "1-HOUR"),
            bar_aggregation=extract_value(nautilus_data.get("bar_aggregation"), "EXTERNAL"),
            trading_node=trading_node,
        )
    else:
        nautilus = NautilusPlatformConfig()

    return PlatformsConfig(hummingbot=hummingbot, nautilus=nautilus, raw=raw_dict)
