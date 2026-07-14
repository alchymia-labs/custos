"""
Position management configuration models (msgspec.Struct for NautilusTrader).

Provides type-safe configuration classes using msgspec.Struct with frozen=True
for compatibility with NautilusTrader's StrategyConfig.
"""

from typing import cast

import msgspec

from ._input import section, value


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
    raw: dict[str, object] | None = None


def build_position_config(
    position_dict: dict[str, object],
    raw_dict: dict[str, object] | None = None,
) -> PositionConfig:
    """Build PositionConfig from YAML dict."""
    if not position_dict:
        return PositionConfig()

    kelly_data = section(position_dict, "kelly")
    kelly = (
        KellyConfig(
            fraction=value(kelly_data, "fraction", 0.25),
            win_rate=value(kelly_data, "win_rate", 0.55),
            payoff_ratio=value(kelly_data, "payoff_ratio", 2.0),
        )
        if kelly_data
        else KellyConfig()
    )

    fixed_risk_data = section(position_dict, "fixed_risk")
    fixed_risk = (
        FixedRiskConfig(risk_pct=value(fixed_risk_data, "risk_pct", 0.01))
        if fixed_risk_data
        else FixedRiskConfig()
    )

    scaling_data = section(position_dict, "scaling")
    if scaling_data:
        scaling = ScalingConfig(
            enabled=value(scaling_data, "enabled", False),
            method=value(scaling_data, "method", "pyramid"),
            max_entries=value(scaling_data, "max_entries", 3),
            entry_interval_pct=value(scaling_data, "entry_interval_pct", 0.02),
            pyramid=PyramidScalingConfig(
                scale_factor=value(section(scaling_data, "pyramid"), "scale_factor", 0.5)
            ),
            fixed=FixedScalingConfig(
                size_per_entry=value(section(scaling_data, "fixed"), "size_per_entry", 0.1)
            ),
            martingale=MartingaleScalingConfig(
                multiplier=value(section(scaling_data, "martingale"), "multiplier", 2.0)
            ),
        )
    else:
        scaling = ScalingConfig()

    limits_data = section(position_dict, "limits")
    if limits_data:
        # Handle correlation_groups conversion from list to tuple
        raw_correlation_groups: list[list[str] | tuple[str, ...]] | tuple[tuple[str, ...], ...] = (
            value(limits_data, "correlation_groups", [])
        )
        if isinstance(raw_correlation_groups, list):
            correlation_groups = tuple(
                tuple(group) if isinstance(group, list) else group
                for group in raw_correlation_groups
            )
        else:
            correlation_groups = raw_correlation_groups

        limits = PositionLimitsConfig(
            max_positions_per_pair=value(limits_data, "max_positions_per_pair", 1),
            min_order_size=value(limits_data, "min_order_size", 10.0),
            max_position_pct=value(limits_data, "max_position_pct", 0.5),
            max_total_positions=value(limits_data, "max_total_positions", 5),
            max_total_exposure=value(limits_data, "max_total_exposure", 0.8),
            max_correlated_exposure=value(limits_data, "max_correlated_exposure", 0.5),
            correlation_groups=correlation_groups,
            max_trade_size=cast(float | None, value(limits_data, "max_trade_size")),
        )
    else:
        limits = PositionLimitsConfig()

    dynamic_sizing_data = section(position_dict, "dynamic_sizing")
    if dynamic_sizing_data:
        vol_adj_data = section(dynamic_sizing_data, "volatility_adjustment")
        volatility_adjustment = (
            VolatilityAdjustmentConfig(
                enabled=value(vol_adj_data, "enabled", False),
                target_volatility=value(vol_adj_data, "target_volatility", 0.02),
                lookback=value(vol_adj_data, "lookback", 20),
                min_multiplier=value(vol_adj_data, "min_multiplier", 0.5),
                max_multiplier=value(vol_adj_data, "max_multiplier", 1.5),
            )
            if vol_adj_data
            else VolatilityAdjustmentConfig()
        )

        streak_adj_data = section(dynamic_sizing_data, "streak_adjustment")
        streak_adjustment = (
            StreakAdjustmentConfig(
                enabled=value(streak_adj_data, "enabled", False),
                loss_reduction=value(streak_adj_data, "loss_reduction", 0.2),
                win_increase=value(streak_adj_data, "win_increase", 0.1),
                max_streak_adjustment=value(streak_adj_data, "max_streak_adjustment", 3),
            )
            if streak_adj_data
            else StreakAdjustmentConfig()
        )

        dynamic_sizing = DynamicSizingConfig(
            enabled=value(dynamic_sizing_data, "enabled", False),
            volatility_adjustment=volatility_adjustment,
            streak_adjustment=streak_adjustment,
        )
    else:
        dynamic_sizing = DynamicSizingConfig()

    return PositionConfig(
        size_type=value(position_dict, "size_type", "percentage"),
        size_value=value(position_dict, "size_value", 0.1),
        capital_mode=value(position_dict, "capital_mode", "compound"),
        initial_capital=value(position_dict, "initial_capital", 10000.0),
        base_size_factor=value(position_dict, "base_size_factor", 1.0),
        kelly=kelly,
        fixed_risk=fixed_risk,
        scaling=scaling,
        limits=limits,
        dynamic_sizing=dynamic_sizing,
        raw=raw_dict,
    )
