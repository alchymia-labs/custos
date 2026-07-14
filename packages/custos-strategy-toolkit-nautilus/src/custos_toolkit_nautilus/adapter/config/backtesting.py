"""
Backtesting configuration models (msgspec.Struct for NautilusTrader).

Provides type-safe configuration classes for Speculum backtesting.
These settings only apply during backtests, not live trading.
"""

import msgspec

from ._input import section, value


class UiConfigSchemaConfig(msgspec.Struct, frozen=True):
    """UI configuration schema for Speculum."""

    sections: tuple[str, ...] = ("parameters", "trading", "position", "risk", "filters")


class DataSourceConfig(msgspec.Struct, frozen=True):
    """Data source configuration for backtesting."""

    provider: str = "databento"  # "databento", "binance", "local"
    warmup_bars: int = 100


class ExecutionModelConfig(msgspec.Struct, frozen=True):
    """Execution model configuration for backtesting."""

    fill_model: str = "realistic"  # "immediate", "realistic", "conservative"
    slippage_model: str = "fixed"  # "fixed", "volume_based", "volatility_based"
    simulated_latency_ms: int = 0


class BacktestingConfig(msgspec.Struct, frozen=True):
    """Backtesting configuration for Speculum."""

    log_indicators: bool = True
    ui_config_schema: UiConfigSchemaConfig = UiConfigSchemaConfig()
    data_source: DataSourceConfig = DataSourceConfig()
    execution_model: ExecutionModelConfig = ExecutionModelConfig()
    raw: dict[str, object] | None = None


def build_backtesting_config(
    backtesting_dict: dict[str, object],
    raw_dict: dict[str, object] | None = None,
) -> BacktestingConfig:
    """Build BacktestingConfig from YAML dict."""
    if not backtesting_dict:
        return BacktestingConfig()

    # UI config schema
    ui_schema_data = section(backtesting_dict, "ui_config_schema")
    if ui_schema_data:
        raw_sections: list[str] | tuple[str, ...] = value(
            ui_schema_data, "sections", ["parameters", "trading", "position", "risk", "filters"]
        )
        sections = tuple(raw_sections) if isinstance(raw_sections, list) else raw_sections
        ui_config_schema = UiConfigSchemaConfig(sections=sections)
    else:
        ui_config_schema = UiConfigSchemaConfig()

    # Data source
    data_source_data = section(backtesting_dict, "data_source")
    if data_source_data:
        data_source = DataSourceConfig(
            provider=value(data_source_data, "provider", "databento"),
            warmup_bars=value(data_source_data, "warmup_bars", 100),
        )
    else:
        data_source = DataSourceConfig()

    # Execution model
    execution_model_data = section(backtesting_dict, "execution_model")
    if execution_model_data:
        execution_model = ExecutionModelConfig(
            fill_model=value(execution_model_data, "fill_model", "realistic"),
            slippage_model=value(execution_model_data, "slippage_model", "fixed"),
            simulated_latency_ms=value(execution_model_data, "simulated_latency_ms", 0),
        )
    else:
        execution_model = ExecutionModelConfig()

    return BacktestingConfig(
        log_indicators=value(backtesting_dict, "log_indicators", True),
        ui_config_schema=ui_config_schema,
        data_source=data_source,
        execution_model=execution_model,
        raw=raw_dict,
    )
