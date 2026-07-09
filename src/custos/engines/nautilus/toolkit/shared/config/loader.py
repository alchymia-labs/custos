"""
Configuration loading utilities.

Provides YAML configuration loading for strategy configs.
Supports the unified config format where each parameter has:
{value: ..., type: ..., title: ..., optimization: ...}

Config is split into:
- base_config.yaml: General settings (trading, position, risk, filters, platforms)
- {strategy}/config.yaml: Strategy-specific settings (strategy, parameters, overrides)

The load_config() function merges both, with strategy config overriding base config.
"""

import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _normalize_yaml_indent(content: str) -> str:
    """
    Normalize YAML indentation markers to spaces.

    Handles:
    - Tab characters → 2 spaces (YAML spec requires spaces)
    - '..' markers at line start → 2 spaces (TradingView Pine Logs export format)

    Args:
        content: Raw YAML content

    Returns:
        Normalized YAML content with proper space indentation
    """
    # Replace tabs with 2 spaces
    content = content.replace("\t", "  ")

    # Replace '..' markers at line start with 2 spaces each
    # Pattern: start of line followed by one or more '..' sequences
    def replace_dots(match: re.Match) -> str:
        dots = match.group(0)
        return " " * len(dots)  # Each '.' becomes one space

    content = re.sub(r"^(?:\.\.)+", replace_dots, content, flags=re.MULTILINE)

    return content


# =============================================================================
# Value Extraction Utility
# =============================================================================


def extract_value(val: Any, default: Any = None) -> Any:
    """
    Extract value from potentially nested config format.

    Handles both:
    - Direct values: "1-HOUR" -> "1-HOUR"
    - Nested schema format: {"value": "1-HOUR", "type": "string"} -> "1-HOUR"

    This is useful when working with raw YAML config that hasn't been
    processed by ConfigWrapper.

    Args:
        val: Value to extract from (may be nested dict or direct value)
        default: Default if val is None

    Returns:
        Extracted value or default

    Examples:
        extract_value("1-HOUR")  # -> "1-HOUR"
        extract_value({"value": "1-HOUR", "type": "string"})  # -> "1-HOUR"
        extract_value(None, "default")  # -> "default"
    """
    if val is None:
        return default
    if isinstance(val, dict) and "value" in val and "type" in val:
        return val["value"]
    return val


# =============================================================================
# ConfigWrapper - Unified Config Format Support
# =============================================================================


class ConfigWrapper:
    """
    Configuration wrapper that supports the unified config format.

    The unified format embeds schema metadata with values:
        parameters:
          atr_period:
            value: 10
            type: integer
            title: "ATR Period"
            optimization: {enabled: true, range: [5, 50], step: 1}

    This wrapper:
    - Extracts pure values for strategy code: config["parameters"]["atr_period"] -> 10
    - Preserves raw config with schema for UI: config.raw["parameters"]["atr_period"] -> {...}
    """

    def __init__(self, data: dict[str, Any]):
        """
        Initialize ConfigWrapper.

        Args:
            data: Raw YAML config dictionary
        """
        self._raw = data
        self._values = self._extract_values(data)

    def _extract_values(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Recursively extract 'value' fields from nested config.

        For each key:
        - If value is a dict with 'value' key: extract the value
        - If value is a dict without 'value' key: recurse
        - Otherwise: keep as-is (simple values like strategy metadata)
        """
        result = {}
        for key, val in data.items():
            if key.startswith("_"):  # Skip metadata like _section
                continue
            if isinstance(val, dict):
                if "value" in val and "type" in val:
                    # This is a config item with schema: {value: ..., type: ...}
                    result[key] = val["value"]
                else:
                    # This is a nested section, recurse
                    extracted = self._extract_values(val)
                    if extracted:  # Only add non-empty sections
                        result[key] = extracted
            else:
                # Simple value (e.g., strategy.name = "SuperTrend")
                result[key] = val
        return result

    def get(self, *keys, default: Any = None) -> Any:
        """
        Get configuration value by keys path.

        Args:
            *keys: Config keys as separate arguments or single dotted string
            default: Default value if key not found

        Returns:
            Extracted value (not the schema dict)

        Examples:
            config.get("trading", "leverage")  # -> 1
            config.get("trading.leverage")     # -> 1
        """
        # Handle both get("a", "b") and get("a.b")
        if len(keys) == 1 and isinstance(keys[0], str) and "." in keys[0]:
            keys = tuple(keys[0].split("."))

        value = self._values
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default

        return value

    def get_raw(self, key: str, default: Any = None) -> Any:
        """
        Get raw config with schema by key.

        Args:
            key: Config key, supports dot notation
            default: Default value if key not found

        Returns:
            Raw config dict including schema metadata
        """
        keys = key.split(".")
        value = self._raw

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default

        return value

    def __getitem__(self, key: str) -> Any:
        """Get extracted value by key."""
        return self._values[key]

    def __contains__(self, key: str) -> bool:
        """Check if key exists in extracted values."""
        return key in self._values

    @property
    def values(self) -> dict[str, Any]:
        """
        Return pure values dictionary (for strategy code).

        This returns the config with 'value' fields extracted,
        providing direct access to configuration values.
        """
        return self._values

    @property
    def raw(self) -> dict[str, Any]:
        """
        Return original config dictionary (for UI/schema).

        This returns the full config including type/title/optimization
        metadata for each parameter.
        """
        return self._raw

    # Convenience properties for common sections
    @property
    def strategy(self) -> dict[str, Any]:
        """Get strategy metadata."""
        return self._values.get("strategy", {})

    @property
    def parameters(self) -> dict[str, Any]:
        """Get strategy parameters."""
        return self._values.get("parameters", {})

    @property
    def trading(self) -> dict[str, Any]:
        """Get trading configuration."""
        return self._values.get("trading", {})

    @property
    def position(self) -> dict[str, Any]:
        """Get position configuration."""
        return self._values.get("position", {})

    @property
    def risk(self) -> dict[str, Any]:
        """Get risk configuration."""
        return self._values.get("risk", {})

    @property
    def filters(self) -> dict[str, Any]:
        """Get filter configuration."""
        return self._values.get("filters", {})

    @property
    def platforms(self) -> dict[str, Any]:
        """Get platform-specific configuration."""
        return self._values.get("platforms", {})

    @property
    def backtesting(self) -> dict[str, Any]:
        """Get backtesting configuration."""
        return self._values.get("backtesting", {})

    @property
    def logging(self) -> dict[str, Any]:
        """Get logging configuration."""
        return self._values.get("logging", {})

    @property
    def warmup(self) -> dict[str, Any] | None:
        """Get warmup configuration."""
        return self._values.get("warmup")

    @property
    def snapshot(self) -> dict[str, Any] | None:
        """Get snapshot persistence configuration."""
        return self._values.get("snapshot")


# =============================================================================
# Deep Merge Utility
# =============================================================================


def deep_merge(base: dict, override: dict) -> dict:
    """
    Deep merge two dictionaries, with override taking precedence.

    Args:
        base: Base dictionary
        override: Override dictionary (values take precedence)

    Returns:
        Merged dictionary
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# =============================================================================
# Configuration Loading
# =============================================================================


def load_config(strategy_config_path: str | Path) -> ConfigWrapper:
    """
    Load and merge base config with strategy config.

    This function:
    1. Loads shared/config/base_config.yaml (general settings)
    2. Loads strategy-specific config.yaml
    3. Deep merges them (strategy overrides base)
    4. Returns ConfigWrapper for easy access

    Args:
        strategy_config_path: Path to strategy's config.yaml

    Returns:
        ConfigWrapper with merged configuration
    """
    strategy_path = Path(strategy_config_path)
    base_path = Path(__file__).parent / "base_config.yaml"

    # Load base config
    base_config: dict[str, Any] = {}
    if base_path.exists():
        with open(base_path, encoding="utf-8") as f:
            content = _normalize_yaml_indent(f.read())
            try:
                base_config = yaml.safe_load(content) or {}
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML in base config {base_path}: {e}") from e
        logger.debug(f"Loaded base config from {base_path}")
    else:
        logger.warning(f"Base config not found at {base_path}")

    # Load strategy config
    strategy_config: dict[str, Any] = {}
    if strategy_path.exists():
        with open(strategy_path, encoding="utf-8") as f:
            content = _normalize_yaml_indent(f.read())
            try:
                strategy_config = yaml.safe_load(content) or {}
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML in strategy config {strategy_path}: {e}") from e
        logger.debug(f"Loaded strategy config from {strategy_path}")
    else:
        raise FileNotFoundError(f"Strategy config not found: {strategy_path}")

    # Merge: strategy overrides base
    merged = deep_merge(base_config, strategy_config)
    logger.info(
        f"Loaded merged config for strategy: {strategy_config.get('strategy', {}).get('name', 'unknown')}"
    )

    return ConfigWrapper(merged)


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    """
    Load a single YAML file without merging.

    Args:
        path: Path to YAML file

    Returns:
        Raw dictionary from YAML file

    Note:
        Indentation is automatically normalized (tabs and '..' markers → spaces).
        This allows direct copy-paste from TradingView Pine Logs output.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, encoding="utf-8") as f:
        content = _normalize_yaml_indent(f.read())
        try:
            return yaml.safe_load(content) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {path}: {e}") from e


# =============================================================================
# Hummingbot Config Conversion
# =============================================================================


def to_hummingbot_config(wrapper: ConfigWrapper, pair: str | None = None) -> dict[str, Any]:
    """
    Convert ConfigWrapper to Hummingbot SuperTrendConfig format.

    Transforms nested YAML structure into flat field format expected by
    the Hummingbot strategy's Config class.

    Args:
        wrapper: ConfigWrapper with merged configuration
        pair: Trading pair to use (defaults to first pair in trading.pairs)

    Returns:
        Dictionary with flat config fields for SuperTrendConfig
    """
    trading = wrapper.trading
    params = wrapper.parameters
    position = wrapper.position
    risk = wrapper.risk
    filters = wrapper.filters
    platforms = wrapper.values.get("platforms", {})
    hb_platform = platforms.get("hummingbot", {})

    # Select trading pair
    trading_pair = pair or (trading.get("pairs", ["BTC-USDT"])[0])

    # Convert direction to enable_long/enable_short
    direction = trading.get("direction", "both").lower()
    enable_long = direction in ("both", "long")
    enable_short = direction in ("both", "short")

    # Build flat config dict
    config = {
        # Exchange settings
        "exchange": trading.get("connector", "binance_perpetual"),
        "trading_pair": trading_pair,
        "leverage": trading.get("leverage", 1),
        "position_mode": trading.get("position_mode", "ONEWAY"),
        "order_type": trading.get("order_type", "market"),
        # K-line data source (use trading settings as defaults)
        "candles_exchange": hb_platform.get("candles_exchange") or trading.get("connector"),
        "candles_pair": hb_platform.get("candles_pair") or trading_pair,
        "candles_interval": hb_platform.get("candles_interval")
        or hb_platform.get("candle_interval", "1h"),
        # Strategy parameters
        "atr_period": params.get("atr_period", 10),
        "atr_multiplier": params.get("atr_multiplier", 3.0),
        # Trading direction
        "enable_long": enable_long,
        "enable_short": enable_short,
        # Position management
        "position_size_type": position.get("size_type", "percentage"),
        "position_size_value": position.get("size_value", 0.1),
        "max_positions_per_pair": position.get("limits", {}).get("max_positions_per_pair", 1),
        "min_order_size": position.get("limits", {}).get("min_order_size", 10),
        # Risk management - from trade section
        "stop_loss_atr_multiplier": risk.get("trade", {})
        .get("stop_loss", {})
        .get("atr", {})
        .get("multiplier", 2.0),
        "take_profit_atr_multiplier": risk.get("trade", {})
        .get("take_profit", {})
        .get("atr", {})
        .get("multiplier", 6.0),
        # Risk management - Fixed SL/TP
        "use_fixed_sl": risk.get("trade", {}).get("stop_loss", {}).get("method") == "fixed",
        "stop_loss": risk.get("trade", {}).get("stop_loss", {}).get("fixed", {}).get("value", 0.02),
        "use_fixed_tp": risk.get("trade", {}).get("take_profit", {}).get("method") == "fixed",
        "take_profit": risk.get("trade", {})
        .get("take_profit", {})
        .get("fixed", {})
        .get("value", 0.04),
        "time_limit": risk.get("trade", {}).get("time_limit", 604800),
        # Trailing stop
        "trailing_stop_enabled": risk.get("trade", {})
        .get("stop_loss", {})
        .get("trailing", {})
        .get("enabled", False),
        "trailing_stop_activation_pct": risk.get("trade", {})
        .get("stop_loss", {})
        .get("trailing", {})
        .get("activation_pct", 0.02),
        "trailing_stop_trailing_pct": risk.get("trade", {})
        .get("stop_loss", {})
        .get("trailing", {})
        .get("trailing_pct", 0.015),
        # Risk limits - from global section
        "max_loss_per_trade_pct": risk.get("trade", {}).get("max_loss_pct", 0.02),
        "max_daily_loss": risk.get("global", {}).get("max_daily_loss", 0.05),
        "consecutive_loss_pause": risk.get("global", {}).get("consecutive_loss_pause", 3),
        # Signal filters
        "volatility_filter_enabled": filters.get("volatility_filter", {}).get("enabled", True),
        "volatility_filter_min_atr_pct": filters.get("volatility_filter", {}).get(
            "min_atr_pct", 0.003
        ),
        "volatility_filter_max_atr_pct": filters.get("volatility_filter", {}).get(
            "max_atr_pct", 0.05
        ),
        "adx_filter_enabled": filters.get("adx_filter", {}).get("enabled", False),
        "adx_period": filters.get("adx_filter", {}).get("period", 14),
        "adx_threshold": filters.get("adx_filter", {}).get("threshold", 25),
        "volume_filter_enabled": filters.get("volume_filter", {}).get("enabled", False),
        "volume_filter_ma_period": filters.get("volume_filter", {}).get("ma_period", 20),
        "volume_filter_threshold": filters.get("volume_filter", {}).get("threshold", 1.2),
    }

    return config
