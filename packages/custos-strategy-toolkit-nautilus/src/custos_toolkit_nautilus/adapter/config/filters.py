"""
Signal filters configuration models (msgspec.Struct for NautilusTrader).

Provides type-safe configuration classes using msgspec.Struct with frozen=True
for compatibility with NautilusTrader's StrategyConfig.
"""

import msgspec

from ._input import section, value


class AdxFilterConfig(msgspec.Struct, frozen=True):
    """ADX filter configuration."""

    enabled: bool = False
    period: int = 14
    threshold: int = 25
    scope: str = "per_pair"


class VolatilityFilterConfig(msgspec.Struct, frozen=True):
    """Volatility filter configuration."""

    enabled: bool = False
    min_atr_pct: float = 0.003
    max_atr_pct: float = 0.05
    atr_lookback: int = 14
    scope: str = "per_pair"


class VolumeFilterConfig(msgspec.Struct, frozen=True):
    """Volume filter configuration."""

    enabled: bool = False
    ma_period: int = 20
    threshold: float = 1.2
    ma_type: str = "ema"  # "ema" or "sma"
    scope: str = "per_pair"


class TimeFilterConfig(msgspec.Struct, frozen=True):
    """Time filter configuration."""

    enabled: bool = False
    trading_hours: str = "00:00-23:59"
    excluded_days: tuple[int, ...] = ()
    excluded_dates: tuple[str, ...] = ()
    scope: str = "global"


class CooldownConfig(msgspec.Struct, frozen=True):
    """Cooldown configuration."""

    min_holding_time: int = 0
    after_exit: int = 0
    after_stop_loss: int = 300
    after_take_profit: int = 0
    scope: str = "per_pair"


class MtfFilterConfig(msgspec.Struct, frozen=True):
    """Multi-timeframe filter configuration."""

    enabled: bool = False
    higher_timeframe: str = "4h"
    alignment_mode: str = "same_direction"  # "same_direction", "not_against"
    scope: str = "per_pair"


class RegimeFilterConfig(msgspec.Struct, frozen=True):
    """Market regime filter configuration.

    Each method reads its own threshold so the scales don't collide:
      - efficiency_ratio: ``trending_threshold`` (0..1 efficiency ratio)
      - atr_percentile:   ``range_pct_threshold`` (price-range/avg, decimal ~0.02-0.05)
      - adx_slope:        rising ADX (slope > 0) over ``lookback``; ADX uses ``adx_period``
    """

    enabled: bool = False
    method: str = "efficiency_ratio"  # "adx_slope", "atr_percentile", "efficiency_ratio"
    lookback: int = 20
    trending_threshold: float = 0.5  # efficiency_ratio only (0..1)
    range_pct_threshold: float = 0.03  # atr_percentile only (price range / avg, decimal)
    adx_period: int = 14  # adx_slope only (ADX indicator period)
    allow_regime: str = "trending"  # "trending", "ranging", "both"
    scope: str = "per_pair"


class RsiConfig(msgspec.Struct, frozen=True):
    """RSI indicator configuration for momentum filter."""

    period: int = 14
    long_min: int = 40
    long_max: int = 70
    short_min: int = 30
    short_max: int = 60


class RocConfig(msgspec.Struct, frozen=True):
    """Rate of Change indicator configuration for momentum filter."""

    period: int = 10
    long_threshold: float = 0.0
    short_threshold: float = 0.0


class MacdConfig(msgspec.Struct, frozen=True):
    """MACD indicator configuration for momentum filter."""

    fast: int = 12
    slow: int = 26
    signal: int = 9
    require_crossover: bool = False
    histogram_positive: bool = True


class MomentumFilterConfig(msgspec.Struct, frozen=True):
    """Momentum filter configuration."""

    enabled: bool = False
    indicator: str = "rsi"  # "rsi", "roc", "macd"
    rsi: RsiConfig = RsiConfig()
    roc: RocConfig = RocConfig()
    macd: MacdConfig = MacdConfig()
    scope: str = "per_pair"


class FilterWeightsConfig(msgspec.Struct, frozen=True):
    """Filter weights for weighted mode."""

    adx_filter: float = 0.3
    volatility_filter: float = 0.25
    volume_filter: float = 0.25
    regime_filter: float = 0.2
    momentum_filter: float = 0.0
    mtf_filter: float = 0.0


class BehaviorConfig(msgspec.Struct, frozen=True):
    """Filter behavior configuration."""

    mode: str = "all"  # "all", "any", "weighted"
    min_score: float = 0.6
    weights: FilterWeightsConfig = FilterWeightsConfig()
    on_filter_fail: str = "skip"  # "skip", "reduce_size", "delay"
    reduce_size_factor: float = 0.5


class FiltersConfig(msgspec.Struct, frozen=True):
    """Signal filters configuration."""

    adx_filter: AdxFilterConfig = AdxFilterConfig()
    volatility_filter: VolatilityFilterConfig = VolatilityFilterConfig()
    volume_filter: VolumeFilterConfig = VolumeFilterConfig()
    time_filter: TimeFilterConfig = TimeFilterConfig()
    cooldown: CooldownConfig = CooldownConfig()
    mtf_filter: MtfFilterConfig = MtfFilterConfig()
    regime_filter: RegimeFilterConfig = RegimeFilterConfig()
    momentum_filter: MomentumFilterConfig = MomentumFilterConfig()
    behavior: BehaviorConfig = BehaviorConfig()
    raw: dict[str, object] | None = None


def build_filters_config(
    filters_dict: dict[str, object],
    raw_dict: dict[str, object] | None = None,
) -> FiltersConfig:
    """Build FiltersConfig from YAML dict."""
    if not filters_dict:
        return FiltersConfig()

    adx_data = section(filters_dict, "adx_filter")
    if adx_data:
        adx = AdxFilterConfig(
            enabled=value(adx_data, "enabled", False),
            period=value(adx_data, "period", 14),
            threshold=value(adx_data, "threshold", 25),
            scope=value(adx_data, "scope", "per_pair"),
        )
    else:
        adx = AdxFilterConfig()

    vol_data = section(filters_dict, "volatility_filter")
    if vol_data:
        volatility = VolatilityFilterConfig(
            enabled=value(vol_data, "enabled", False),
            min_atr_pct=value(vol_data, "min_atr_pct", 0.003),
            max_atr_pct=value(vol_data, "max_atr_pct", 0.05),
            atr_lookback=value(vol_data, "atr_lookback", 14),
            scope=value(vol_data, "scope", "per_pair"),
        )
    else:
        volatility = VolatilityFilterConfig()

    volume_data = section(filters_dict, "volume_filter")
    if volume_data:
        volume = VolumeFilterConfig(
            enabled=value(volume_data, "enabled", False),
            ma_period=value(volume_data, "ma_period", 20),
            threshold=value(volume_data, "threshold", 1.2),
            ma_type=value(volume_data, "ma_type", "ema"),
            scope=value(volume_data, "scope", "per_pair"),
        )
    else:
        volume = VolumeFilterConfig()

    time_data = section(filters_dict, "time_filter")
    if time_data:
        excluded_days: list[int] | tuple[int, ...] = value(time_data, "excluded_days", [])
        excluded_dates: list[str] | tuple[str, ...] = value(time_data, "excluded_dates", [])
        time_filter = TimeFilterConfig(
            enabled=value(time_data, "enabled", False),
            trading_hours=value(time_data, "trading_hours", "00:00-23:59"),
            excluded_days=tuple(excluded_days)
            if isinstance(excluded_days, list)
            else excluded_days,
            excluded_dates=tuple(excluded_dates)
            if isinstance(excluded_dates, list)
            else excluded_dates,
            scope=value(time_data, "scope", "global"),
        )
    else:
        time_filter = TimeFilterConfig()

    cooldown_data = section(filters_dict, "cooldown")
    if cooldown_data:
        cooldown = CooldownConfig(
            min_holding_time=value(cooldown_data, "min_holding_time", 0),
            after_exit=value(cooldown_data, "after_exit", 0),
            after_stop_loss=value(cooldown_data, "after_stop_loss", 300),
            after_take_profit=value(cooldown_data, "after_take_profit", 0),
            scope=value(cooldown_data, "scope", "per_pair"),
        )
    else:
        cooldown = CooldownConfig()

    mtf_data = section(filters_dict, "mtf_filter")
    if mtf_data:
        mtf_filter = MtfFilterConfig(
            enabled=value(mtf_data, "enabled", False),
            higher_timeframe=value(mtf_data, "higher_timeframe", "4h"),
            alignment_mode=value(mtf_data, "alignment_mode", "same_direction"),
            scope=value(mtf_data, "scope", "per_pair"),
        )
    else:
        mtf_filter = MtfFilterConfig()

    regime_data = section(filters_dict, "regime_filter")
    if regime_data:
        regime_filter = RegimeFilterConfig(
            enabled=value(regime_data, "enabled", False),
            method=value(regime_data, "method", "efficiency_ratio"),
            lookback=value(regime_data, "lookback", 20),
            trending_threshold=value(regime_data, "trending_threshold", 0.5),
            range_pct_threshold=value(regime_data, "range_pct_threshold", 0.03),
            adx_period=value(regime_data, "adx_period", 14),
            allow_regime=value(regime_data, "allow_regime", "trending"),
            scope=value(regime_data, "scope", "per_pair"),
        )
    else:
        regime_filter = RegimeFilterConfig()

    momentum_data = section(filters_dict, "momentum_filter")
    if momentum_data:
        rsi_data = section(momentum_data, "rsi")
        roc_data = section(momentum_data, "roc")
        macd_data = section(momentum_data, "macd")

        rsi = (
            RsiConfig(
                period=value(rsi_data, "period", 14),
                long_min=value(rsi_data, "long_min", 40),
                long_max=value(rsi_data, "long_max", 70),
                short_min=value(rsi_data, "short_min", 30),
                short_max=value(rsi_data, "short_max", 60),
            )
            if rsi_data
            else RsiConfig()
        )

        roc = (
            RocConfig(
                period=value(roc_data, "period", 10),
                long_threshold=value(roc_data, "long_threshold", 0.0),
                short_threshold=value(roc_data, "short_threshold", 0.0),
            )
            if roc_data
            else RocConfig()
        )

        macd = (
            MacdConfig(
                fast=value(macd_data, "fast", 12),
                slow=value(macd_data, "slow", 26),
                signal=value(macd_data, "signal", 9),
                require_crossover=value(macd_data, "require_crossover", False),
                histogram_positive=value(macd_data, "histogram_positive", True),
            )
            if macd_data
            else MacdConfig()
        )

        momentum_filter = MomentumFilterConfig(
            enabled=value(momentum_data, "enabled", False),
            indicator=value(momentum_data, "indicator", "rsi"),
            rsi=rsi,
            roc=roc,
            macd=macd,
            scope=value(momentum_data, "scope", "per_pair"),
        )
    else:
        momentum_filter = MomentumFilterConfig()

    behavior_data = section(filters_dict, "behavior")
    if behavior_data:
        weights_data = section(behavior_data, "weights")
        weights = (
            FilterWeightsConfig(
                adx_filter=value(weights_data, "adx_filter", 0.3),
                volatility_filter=value(weights_data, "volatility_filter", 0.25),
                volume_filter=value(weights_data, "volume_filter", 0.25),
                regime_filter=value(weights_data, "regime_filter", 0.2),
                momentum_filter=value(weights_data, "momentum_filter", 0.0),
                mtf_filter=value(weights_data, "mtf_filter", 0.0),
            )
            if weights_data
            else FilterWeightsConfig()
        )

        behavior = BehaviorConfig(
            mode=value(behavior_data, "mode", "all"),
            min_score=value(behavior_data, "min_score", 0.6),
            weights=weights,
            on_filter_fail=value(behavior_data, "on_filter_fail", "skip"),
            reduce_size_factor=value(behavior_data, "reduce_size_factor", 0.5),
        )
    else:
        behavior = BehaviorConfig()

    return FiltersConfig(
        adx_filter=adx,
        volatility_filter=volatility,
        volume_filter=volume,
        time_filter=time_filter,
        cooldown=cooldown,
        mtf_filter=mtf_filter,
        regime_filter=regime_filter,
        momentum_filter=momentum_filter,
        behavior=behavior,
        raw=raw_dict,
    )
