"""
Signal filters configuration models (msgspec.Struct for NautilusTrader).

Provides type-safe configuration classes using msgspec.Struct with frozen=True
for compatibility with NautilusTrader's StrategyConfig.
"""

import msgspec


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
    raw: dict | None = None


def build_filters_config(filters_dict: dict, raw_dict: dict | None = None) -> FiltersConfig:
    """Build FiltersConfig from YAML dict."""
    if not filters_dict:
        return FiltersConfig()

    adx_data = filters_dict.get("adx_filter", {})
    if adx_data:
        adx = AdxFilterConfig(
            enabled=adx_data.get("enabled", False),
            period=adx_data.get("period", 14),
            threshold=adx_data.get("threshold", 25),
            scope=adx_data.get("scope", "per_pair"),
        )
    else:
        adx = AdxFilterConfig()

    vol_data = filters_dict.get("volatility_filter", {})
    if vol_data:
        volatility = VolatilityFilterConfig(
            enabled=vol_data.get("enabled", False),
            min_atr_pct=vol_data.get("min_atr_pct", 0.003),
            max_atr_pct=vol_data.get("max_atr_pct", 0.05),
            atr_lookback=vol_data.get("atr_lookback", 14),
            scope=vol_data.get("scope", "per_pair"),
        )
    else:
        volatility = VolatilityFilterConfig()

    volume_data = filters_dict.get("volume_filter", {})
    if volume_data:
        volume = VolumeFilterConfig(
            enabled=volume_data.get("enabled", False),
            ma_period=volume_data.get("ma_period", 20),
            threshold=volume_data.get("threshold", 1.2),
            ma_type=volume_data.get("ma_type", "ema"),
            scope=volume_data.get("scope", "per_pair"),
        )
    else:
        volume = VolumeFilterConfig()

    time_data = filters_dict.get("time_filter", {})
    if time_data:
        excluded_days = time_data.get("excluded_days", [])
        excluded_dates = time_data.get("excluded_dates", [])
        time_filter = TimeFilterConfig(
            enabled=time_data.get("enabled", False),
            trading_hours=time_data.get("trading_hours", "00:00-23:59"),
            excluded_days=tuple(excluded_days)
            if isinstance(excluded_days, list)
            else excluded_days,
            excluded_dates=tuple(excluded_dates)
            if isinstance(excluded_dates, list)
            else excluded_dates,
            scope=time_data.get("scope", "global"),
        )
    else:
        time_filter = TimeFilterConfig()

    cooldown_data = filters_dict.get("cooldown", {})
    if cooldown_data:
        cooldown = CooldownConfig(
            min_holding_time=cooldown_data.get("min_holding_time", 0),
            after_exit=cooldown_data.get("after_exit", 0),
            after_stop_loss=cooldown_data.get("after_stop_loss", 300),
            after_take_profit=cooldown_data.get("after_take_profit", 0),
            scope=cooldown_data.get("scope", "per_pair"),
        )
    else:
        cooldown = CooldownConfig()

    mtf_data = filters_dict.get("mtf_filter", {})
    if mtf_data:
        mtf_filter = MtfFilterConfig(
            enabled=mtf_data.get("enabled", False),
            higher_timeframe=mtf_data.get("higher_timeframe", "4h"),
            alignment_mode=mtf_data.get("alignment_mode", "same_direction"),
            scope=mtf_data.get("scope", "per_pair"),
        )
    else:
        mtf_filter = MtfFilterConfig()

    regime_data = filters_dict.get("regime_filter", {})
    if regime_data:
        regime_filter = RegimeFilterConfig(
            enabled=regime_data.get("enabled", False),
            method=regime_data.get("method", "efficiency_ratio"),
            lookback=regime_data.get("lookback", 20),
            trending_threshold=regime_data.get("trending_threshold", 0.5),
            range_pct_threshold=regime_data.get("range_pct_threshold", 0.03),
            adx_period=regime_data.get("adx_period", 14),
            allow_regime=regime_data.get("allow_regime", "trending"),
            scope=regime_data.get("scope", "per_pair"),
        )
    else:
        regime_filter = RegimeFilterConfig()

    momentum_data = filters_dict.get("momentum_filter", {})
    if momentum_data:
        rsi_data = momentum_data.get("rsi", {})
        roc_data = momentum_data.get("roc", {})
        macd_data = momentum_data.get("macd", {})

        rsi = (
            RsiConfig(
                period=rsi_data.get("period", 14),
                long_min=rsi_data.get("long_min", 40),
                long_max=rsi_data.get("long_max", 70),
                short_min=rsi_data.get("short_min", 30),
                short_max=rsi_data.get("short_max", 60),
            )
            if rsi_data
            else RsiConfig()
        )

        roc = (
            RocConfig(
                period=roc_data.get("period", 10),
                long_threshold=roc_data.get("long_threshold", 0.0),
                short_threshold=roc_data.get("short_threshold", 0.0),
            )
            if roc_data
            else RocConfig()
        )

        macd = (
            MacdConfig(
                fast=macd_data.get("fast", 12),
                slow=macd_data.get("slow", 26),
                signal=macd_data.get("signal", 9),
                require_crossover=macd_data.get("require_crossover", False),
                histogram_positive=macd_data.get("histogram_positive", True),
            )
            if macd_data
            else MacdConfig()
        )

        momentum_filter = MomentumFilterConfig(
            enabled=momentum_data.get("enabled", False),
            indicator=momentum_data.get("indicator", "rsi"),
            rsi=rsi,
            roc=roc,
            macd=macd,
            scope=momentum_data.get("scope", "per_pair"),
        )
    else:
        momentum_filter = MomentumFilterConfig()

    behavior_data = filters_dict.get("behavior", {})
    if behavior_data:
        weights_data = behavior_data.get("weights", {})
        weights = (
            FilterWeightsConfig(
                adx_filter=weights_data.get("adx_filter", 0.3),
                volatility_filter=weights_data.get("volatility_filter", 0.25),
                volume_filter=weights_data.get("volume_filter", 0.25),
                regime_filter=weights_data.get("regime_filter", 0.2),
                momentum_filter=weights_data.get("momentum_filter", 0.0),
                mtf_filter=weights_data.get("mtf_filter", 0.0),
            )
            if weights_data
            else FilterWeightsConfig()
        )

        behavior = BehaviorConfig(
            mode=behavior_data.get("mode", "all"),
            min_score=behavior_data.get("min_score", 0.6),
            weights=weights,
            on_filter_fail=behavior_data.get("on_filter_fail", "skip"),
            reduce_size_factor=behavior_data.get("reduce_size_factor", 0.5),
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
