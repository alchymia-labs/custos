"""
NautilusTrader configuration models (msgspec.Struct-based).

Provides type-safe configuration classes for NautilusTrader strategies.
These use msgspec.Struct with frozen=True for compatibility with
NautilusTrader's StrategyConfig.
"""

# Backtesting configuration
# Allocation configuration
from .allocation import (
    AllocationConfig,
    build_allocation_config,
)
from .backtesting import (
    BacktestingConfig,
    DataSourceConfig,
    ExecutionModelConfig,
    UiConfigSchemaConfig,
    build_backtesting_config,
)

# Signal filters configuration
from .filters import (
    AdxFilterConfig,
    BehaviorConfig,
    CooldownConfig,
    FiltersConfig,
    FilterWeightsConfig,
    MacdConfig,
    MomentumFilterConfig,
    MtfFilterConfig,
    RegimeFilterConfig,
    RocConfig,
    RsiConfig,
    TimeFilterConfig,
    VolatilityFilterConfig,
    VolumeFilterConfig,
    build_filters_config,
)

# Platform configuration
from .platforms import (
    DatabaseConfig,
    HummingbotPlatformConfig,
    NautilusPlatformConfig,
    PlatformsConfig,
    TradingNodeConfig,
    build_platforms_config,
)

# Position management configuration
from .position import (
    DynamicSizingConfig,
    FixedRiskConfig,
    FixedScalingConfig,
    KellyConfig,
    MartingaleScalingConfig,
    PositionConfig,
    PositionLimitsConfig,
    PyramidScalingConfig,
    ScalingConfig,
    StreakAdjustmentConfig,
    VolatilityAdjustmentConfig,
    build_position_config,
)

# Risk management configuration
from .risk import (
    BreakEvenConfig,
    GlobalRiskConfig,
    RiskConfig,
    ScaledTakeProfitConfig,
    ScaledTakeProfitLevelConfig,
    StopLossAtrConfig,
    StopLossConfig,
    StopLossFixedConfig,
    StopLossIndicatorConfig,
    StopLossTrailingConfig,
    TakeProfitAtrConfig,
    TakeProfitConfig,
    TakeProfitFixedConfig,
    TakeProfitTrailingConfig,
    TickMonitoringConfig,
    TradeRiskConfig,
    build_risk_config,
)

# Signal configuration (OKX compatibility)
from .signal import (
    OkxConfig,
    SignalConfig,
    SignalDefaultsConfig,
    build_signal_config,
)

# Snapshot configuration
from .snapshot import (
    SnapshotConfig,
    build_snapshot_config,
)

# Trading configuration
from .trading import (
    ExecutionConfig,
    FeeConfig,
    PriceImprovementConfig,
    SplitOrdersConfig,
    TradingConfig,
    build_trading_config,
)

__all__ = [
    # Backtesting
    "BacktestingConfig",
    "DataSourceConfig",
    "ExecutionModelConfig",
    "UiConfigSchemaConfig",
    "build_backtesting_config",
    # Trading
    "FeeConfig",
    "SplitOrdersConfig",
    "PriceImprovementConfig",
    "ExecutionConfig",
    "TradingConfig",
    "build_trading_config",
    # Position
    "KellyConfig",
    "FixedRiskConfig",
    "PyramidScalingConfig",
    "FixedScalingConfig",
    "MartingaleScalingConfig",
    "ScalingConfig",
    "PositionLimitsConfig",
    "VolatilityAdjustmentConfig",
    "StreakAdjustmentConfig",
    "DynamicSizingConfig",
    "PositionConfig",
    "build_position_config",
    # Risk
    "GlobalRiskConfig",
    "TakeProfitAtrConfig",
    "TakeProfitFixedConfig",
    "TakeProfitTrailingConfig",
    "ScaledTakeProfitLevelConfig",
    "ScaledTakeProfitConfig",
    "TakeProfitConfig",
    "StopLossAtrConfig",
    "StopLossFixedConfig",
    "StopLossTrailingConfig",
    "StopLossIndicatorConfig",
    "BreakEvenConfig",
    "StopLossConfig",
    "TradeRiskConfig",
    "TickMonitoringConfig",
    "RiskConfig",
    "build_risk_config",
    # Filters
    "AdxFilterConfig",
    "VolatilityFilterConfig",
    "VolumeFilterConfig",
    "TimeFilterConfig",
    "CooldownConfig",
    "MtfFilterConfig",
    "RegimeFilterConfig",
    "RsiConfig",
    "RocConfig",
    "MacdConfig",
    "MomentumFilterConfig",
    "FilterWeightsConfig",
    "BehaviorConfig",
    "FiltersConfig",
    "build_filters_config",
    # Platforms
    "DatabaseConfig",
    "HummingbotPlatformConfig",
    "NautilusPlatformConfig",
    "PlatformsConfig",
    "TradingNodeConfig",
    "build_platforms_config",
    # Snapshot
    "SnapshotConfig",
    "build_snapshot_config",
    # Signal (OKX compatibility)
    "OkxConfig",
    "SignalConfig",
    "SignalDefaultsConfig",
    "build_signal_config",
    # Allocation
    "AllocationConfig",
    "build_allocation_config",
]
