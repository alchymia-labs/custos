"""
Position management configuration models (msgspec.Struct for NautilusTrader).

Provides type-safe configuration classes using msgspec.Struct with frozen=True
for compatibility with NautilusTrader's StrategyConfig.
"""

import msgspec


class KellyConfig(msgspec.Struct, frozen=True):
    """Kelly criterion configuration."""

    fraction: float = 0.25
    win_rate: float = 0.55
    payoff_ratio: float = 2.0


class FixedRiskConfig(msgspec.Struct, frozen=True):
    """Fixed-risk sizing configuration (size_type="fixed_risk").

    Sizes a position so that hitting the stop-loss loses ``risk_pct`` of equity,
    via the native NautilusTrader FixedRiskSizer.

    risk_pct is a DECIMAL fraction: 0.01 == 1%, NOT 0.01%.
    """

    risk_pct: float = 0.01


class PyramidScalingConfig(msgspec.Struct, frozen=True):
    """Pyramid scaling configuration."""

    scale_factor: float = 0.5


class FixedScalingConfig(msgspec.Struct, frozen=True):
    """Fixed scaling configuration."""

    size_per_entry: float = 0.1


class MartingaleScalingConfig(msgspec.Struct, frozen=True):
    """Martingale scaling configuration."""

    multiplier: float = 2.0


class ScalingConfig(msgspec.Struct, frozen=True):
    """Position scaling configuration."""

    enabled: bool = False
    method: str = "pyramid"
    max_entries: int = 3
    entry_interval_pct: float = 0.02
    pyramid: PyramidScalingConfig = PyramidScalingConfig()
    fixed: FixedScalingConfig = FixedScalingConfig()
    martingale: MartingaleScalingConfig = MartingaleScalingConfig()


class PositionLimitsConfig(msgspec.Struct, frozen=True):
    """Position limits configuration."""

    max_positions_per_pair: int = 1
    min_order_size: float = 10.0
    max_position_pct: float = 0.5
    max_total_positions: int = 5
    max_total_exposure: float = 0.8
    max_correlated_exposure: float = 0.5
    correlation_groups: tuple[tuple[str, ...], ...] = ()
    max_trade_size: float | None = None  # Absolute max order size (exchange limit)


class VolatilityAdjustmentConfig(msgspec.Struct, frozen=True):
    """Volatility-based position size adjustment."""

    enabled: bool = False
    target_volatility: float = 0.02
    lookback: int = 20
    min_multiplier: float = 0.5
    max_multiplier: float = 1.5


class StreakAdjustmentConfig(msgspec.Struct, frozen=True):
    """Win/loss streak-based position size adjustment."""

    enabled: bool = False
    loss_reduction: float = 0.2
    win_increase: float = 0.1
    max_streak_adjustment: int = 3


class DynamicSizingConfig(msgspec.Struct, frozen=True):
    """Dynamic position sizing configuration."""

    enabled: bool = False
    volatility_adjustment: VolatilityAdjustmentConfig = VolatilityAdjustmentConfig()
    streak_adjustment: StreakAdjustmentConfig = StreakAdjustmentConfig()


class PositionConfig(msgspec.Struct, frozen=True):
    """Position management configuration.

    size_type selects the sizing mode:
      - "percentage" / "fixed" / "kelly": notional (quote) amount model (size_value).
      - "fixed_risk": base quantity derived from stop-loss distance via the native
        FixedRiskSizer (uses ``fixed_risk.risk_pct``; requires a valid stop-loss).
    """

    size_type: str = "percentage"
    size_value: float = 0.1
    capital_mode: str = "compound"
    initial_capital: float = 10000.0
    base_size_factor: float = 1.0  # Global position size multiplier (0.0-1.0)
    kelly: KellyConfig = KellyConfig()
    fixed_risk: FixedRiskConfig = FixedRiskConfig()
    scaling: ScalingConfig = ScalingConfig()
    limits: PositionLimitsConfig = PositionLimitsConfig()
    dynamic_sizing: DynamicSizingConfig = DynamicSizingConfig()
    raw: dict | None = None


def build_position_config(position_dict: dict, raw_dict: dict | None = None) -> PositionConfig:
    """Build PositionConfig from YAML dict."""
    if not position_dict:
        return PositionConfig()

    kelly_data = position_dict.get("kelly", {})
    kelly = KellyConfig(**kelly_data) if kelly_data else KellyConfig()

    fixed_risk_data = position_dict.get("fixed_risk", {})
    fixed_risk = FixedRiskConfig(**fixed_risk_data) if fixed_risk_data else FixedRiskConfig()

    scaling_data = position_dict.get("scaling", {})
    if scaling_data:
        scaling = ScalingConfig(
            enabled=scaling_data.get("enabled", False),
            method=scaling_data.get("method", "pyramid"),
            max_entries=scaling_data.get("max_entries", 3),
            entry_interval_pct=scaling_data.get("entry_interval_pct", 0.02),
            pyramid=PyramidScalingConfig(**scaling_data.get("pyramid", {})),
            fixed=FixedScalingConfig(**scaling_data.get("fixed", {})),
            martingale=MartingaleScalingConfig(**scaling_data.get("martingale", {})),
        )
    else:
        scaling = ScalingConfig()

    limits_data = position_dict.get("limits", {})
    if limits_data:
        # Handle correlation_groups conversion from list to tuple
        correlation_groups = limits_data.get("correlation_groups", [])
        if isinstance(correlation_groups, list):
            correlation_groups = tuple(
                tuple(group) if isinstance(group, list) else group for group in correlation_groups
            )

        limits = PositionLimitsConfig(
            max_positions_per_pair=limits_data.get("max_positions_per_pair", 1),
            min_order_size=limits_data.get("min_order_size", 10.0),
            max_position_pct=limits_data.get("max_position_pct", 0.5),
            max_total_positions=limits_data.get("max_total_positions", 5),
            max_total_exposure=limits_data.get("max_total_exposure", 0.8),
            max_correlated_exposure=limits_data.get("max_correlated_exposure", 0.5),
            correlation_groups=correlation_groups,
            max_trade_size=limits_data.get("max_trade_size"),
        )
    else:
        limits = PositionLimitsConfig()

    dynamic_sizing_data = position_dict.get("dynamic_sizing", {})
    if dynamic_sizing_data:
        vol_adj_data = dynamic_sizing_data.get("volatility_adjustment", {})
        volatility_adjustment = (
            VolatilityAdjustmentConfig(**vol_adj_data)
            if vol_adj_data
            else VolatilityAdjustmentConfig()
        )

        streak_adj_data = dynamic_sizing_data.get("streak_adjustment", {})
        streak_adjustment = (
            StreakAdjustmentConfig(**streak_adj_data)
            if streak_adj_data
            else StreakAdjustmentConfig()
        )

        dynamic_sizing = DynamicSizingConfig(
            enabled=dynamic_sizing_data.get("enabled", False),
            volatility_adjustment=volatility_adjustment,
            streak_adjustment=streak_adjustment,
        )
    else:
        dynamic_sizing = DynamicSizingConfig()

    return PositionConfig(
        size_type=position_dict.get("size_type", "percentage"),
        size_value=position_dict.get("size_value", 0.1),
        capital_mode=position_dict.get("capital_mode", "compound"),
        initial_capital=position_dict.get("initial_capital", 10000.0),
        base_size_factor=position_dict.get("base_size_factor", 1.0),
        kelly=kelly,
        fixed_risk=fixed_risk,
        scaling=scaling,
        limits=limits,
        dynamic_sizing=dynamic_sizing,
        raw=raw_dict,
    )
