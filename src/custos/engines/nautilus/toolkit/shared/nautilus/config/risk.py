"""
Risk management configuration models (msgspec.Struct for NautilusTrader).

Provides type-safe configuration classes using msgspec.Struct with frozen=True
for compatibility with NautilusTrader's StrategyConfig.
"""

import msgspec


class GlobalRiskConfig(msgspec.Struct, frozen=True):
    """Global risk management configuration."""

    max_daily_loss: float = 0.05
    max_drawdown: float = 0.10
    consecutive_loss_pause: int = 3
    max_daily_trades: int = 0  # 0 = unlimited
    max_daily_profit: float = 0.0  # 0 = unlimited
    reset_time: str = "00:00"  # UTC; daily session counters reset at this boundary
    pause_duration: int = 0  # seconds; 0 = pause until next reset boundary

    def __post_init__(self) -> None:
        # fail-fast on config typos: a negative pause or malformed reset_time would
        # otherwise silently disable the daily reset / pause-until-next-day path.
        if self.pause_duration < 0:
            raise ValueError(f"pause_duration must be >= 0, got {self.pause_duration}")
        parts = self.reset_time.split(":")
        valid = len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit()
        if valid:
            hour, minute = int(parts[0]), int(parts[1])
            valid = 0 <= hour <= 23 and 0 <= minute <= 59
        if not valid:
            raise ValueError(f"reset_time must be 'HH:MM' (24h UTC), got {self.reset_time!r}")
        # Ratio fields are decimals in [0, 1]; a value like 5.0 (a 5% limit miswritten
        # as 5.0) must fail-fast instead of silently arming a 500% threshold.
        for name, value in (
            ("max_daily_loss", self.max_daily_loss),
            ("max_drawdown", self.max_drawdown),
            ("max_daily_profit", self.max_daily_profit),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be a ratio in [0, 1] (e.g. 0.05 = 5%), got {value}")


class TakeProfitAtrConfig(msgspec.Struct, frozen=True):
    """ATR-based take profit configuration."""

    multiplier: float = 6.0


class TakeProfitFixedConfig(msgspec.Struct, frozen=True):
    """Fixed take profit configuration."""

    value: float = 0.04


class TakeProfitTrailingConfig(msgspec.Struct, frozen=True):
    """Trailing take profit configuration."""

    activation_pct: float = 0.03
    callback_pct: float = 0.01


class ScaledTakeProfitLevelConfig(msgspec.Struct, frozen=True):
    """Single level configuration for scaled take profit."""

    target_pct: float = 0.02
    exit_pct: float = 0.33


class ScaledTakeProfitConfig(msgspec.Struct, frozen=True):
    """Scaled (multi-level) take profit configuration."""

    levels: int = 3
    level_1: ScaledTakeProfitLevelConfig = ScaledTakeProfitLevelConfig(
        target_pct=0.02, exit_pct=0.33
    )
    level_2: ScaledTakeProfitLevelConfig = ScaledTakeProfitLevelConfig(
        target_pct=0.04, exit_pct=0.33
    )
    level_3: ScaledTakeProfitLevelConfig = ScaledTakeProfitLevelConfig(
        target_pct=0.06, exit_pct=0.34
    )


class TakeProfitConfig(msgspec.Struct, frozen=True):
    """Take profit configuration."""

    method: str = "atr"
    atr: TakeProfitAtrConfig = TakeProfitAtrConfig()
    fixed: TakeProfitFixedConfig = TakeProfitFixedConfig()
    trailing: TakeProfitTrailingConfig = TakeProfitTrailingConfig()
    scaled: ScaledTakeProfitConfig = ScaledTakeProfitConfig()


class StopLossAtrConfig(msgspec.Struct, frozen=True):
    """ATR-based stop loss configuration."""

    multiplier: float = 2.0


class StopLossFixedConfig(msgspec.Struct, frozen=True):
    """Fixed stop loss configuration."""

    value: float = 0.02


class StopLossTrailingConfig(msgspec.Struct, frozen=True):
    """Trailing stop loss configuration."""

    enabled: bool = False
    activation_pct: float = 0.02
    trailing_pct: float = 0.015
    # Trigger price reference for the exchange-managed native trailing stop
    # (TrailingStopMarketOrder). One of "default" / "last" / "mark";
    # mark price avoids last-price wicks on contract protective orders. Unused by
    # the legacy tick/hybrid trailing path. Backward-compatible default.
    trigger_price_type: str = "mark"


class StopLossIndicatorConfig(msgspec.Struct, frozen=True):
    """Indicator-based stop loss configuration."""

    type: str = "supertrend"


class BreakEvenConfig(msgspec.Struct, frozen=True):
    """Break-even stop loss configuration."""

    enabled: bool = False
    activation_pct: float = 0.015
    offset: float = 0.001


class StopLossConfig(msgspec.Struct, frozen=True):
    """Stop loss configuration."""

    method: str = "atr"
    atr: StopLossAtrConfig = StopLossAtrConfig()
    fixed: StopLossFixedConfig = StopLossFixedConfig()
    trailing: StopLossTrailingConfig = StopLossTrailingConfig()
    indicator: StopLossIndicatorConfig = StopLossIndicatorConfig()
    break_even: BreakEvenConfig = BreakEvenConfig()


# Valid SL/TP execution modes (single source of truth for __post_init__ validation
# and external references).
SL_TP_MODES: tuple[str, ...] = ("exchange", "tick", "hybrid", "native_trailing")


class TradeRiskConfig(msgspec.Struct, frozen=True):
    """Per-trade risk configuration."""

    sl_tp_mode: str = "hybrid"  # valid values: see SL_TP_MODES
    max_loss_pct: float = 0.02
    time_limit: int = 604800
    atr_period: int = 14  # Shared ATR period for SL/TP calculations
    take_profit: TakeProfitConfig = TakeProfitConfig()
    stop_loss: StopLossConfig = StopLossConfig()

    def __post_init__(self) -> None:
        # fail-fast: reject an invalid sl_tp_mode at construction time rather than
        # silently falling back. A config typo must not make the actual SL/TP mode
        # differ from the intent. The direct-construction path (build_risk_config) is
        # not validated by Literal, so intercept it explicitly here.
        if self.sl_tp_mode not in SL_TP_MODES:
            raise ValueError(
                f"sl_tp_mode={self.sl_tp_mode!r} is invalid; valid values: {SL_TP_MODES}. "
                "Check the spelling of risk.trade.sl_tp_mode in config.yaml."
            )
        # max_loss_pct is a decimal in (0, 1]; 5.0 (a 5% limit miswritten as 5.0) or
        # 0/negative must fail-fast rather than silently arming a 500% / no-op limit.
        if not 0 < self.max_loss_pct <= 1:
            raise ValueError(
                f"max_loss_pct must be a ratio in (0, 1] (e.g. 0.02 = 2%), got {self.max_loss_pct}"
            )


class TickMonitoringConfig(msgspec.Struct, frozen=True):
    """Configuration for tick-level position monitoring."""

    enabled: bool = False
    tick_type: str = "trade"  # "trade", "quote", or "both"


class RiskConfig(msgspec.Struct, frozen=True):
    """Risk management configuration."""

    global_risk: GlobalRiskConfig = GlobalRiskConfig()
    trade: TradeRiskConfig = TradeRiskConfig()
    tick_monitoring: TickMonitoringConfig = TickMonitoringConfig()
    raw: dict | None = None


def build_risk_config(risk_dict: dict, raw_dict: dict | None = None) -> RiskConfig:
    """Build RiskConfig from YAML dict."""
    if not risk_dict:
        return RiskConfig()

    global_data = risk_dict.get("global", {})
    if global_data:
        global_risk = GlobalRiskConfig(
            max_daily_loss=global_data.get("max_daily_loss", 0.05),
            max_drawdown=global_data.get("max_drawdown", 0.10),
            consecutive_loss_pause=global_data.get("consecutive_loss_pause", 3),
            max_daily_trades=global_data.get("max_daily_trades", 0),
            max_daily_profit=global_data.get("max_daily_profit", 0.0),
            reset_time=global_data.get("reset_time", "00:00"),
            pause_duration=global_data.get("pause_duration", 0),
        )
    else:
        global_risk = GlobalRiskConfig()

    trade_data = risk_dict.get("trade", {})
    if trade_data:
        tp_data = trade_data.get("take_profit", {})
        if tp_data:
            # Build scaled take profit config
            scaled_data = tp_data.get("scaled", {})
            if scaled_data:
                level_1_data = scaled_data.get("level_1", {})
                level_2_data = scaled_data.get("level_2", {})
                level_3_data = scaled_data.get("level_3", {})
                scaled = ScaledTakeProfitConfig(
                    levels=scaled_data.get("levels", 3),
                    level_1=ScaledTakeProfitLevelConfig(**level_1_data)
                    if level_1_data
                    else ScaledTakeProfitLevelConfig(target_pct=0.02, exit_pct=0.33),
                    level_2=ScaledTakeProfitLevelConfig(**level_2_data)
                    if level_2_data
                    else ScaledTakeProfitLevelConfig(target_pct=0.04, exit_pct=0.33),
                    level_3=ScaledTakeProfitLevelConfig(**level_3_data)
                    if level_3_data
                    else ScaledTakeProfitLevelConfig(target_pct=0.06, exit_pct=0.34),
                )
            else:
                scaled = ScaledTakeProfitConfig()

            take_profit = TakeProfitConfig(
                method=tp_data.get("method", "atr"),
                atr=TakeProfitAtrConfig(**tp_data.get("atr", {})),
                fixed=TakeProfitFixedConfig(**tp_data.get("fixed", {})),
                trailing=TakeProfitTrailingConfig(**tp_data.get("trailing", {})),
                scaled=scaled,
            )
        else:
            take_profit = TakeProfitConfig()

        sl_data = trade_data.get("stop_loss", {})
        if sl_data:
            break_even_data = sl_data.get("break_even", {})
            break_even = (
                BreakEvenConfig(**break_even_data) if break_even_data else BreakEvenConfig()
            )

            stop_loss = StopLossConfig(
                method=sl_data.get("method", "atr"),
                atr=StopLossAtrConfig(**sl_data.get("atr", {})),
                fixed=StopLossFixedConfig(**sl_data.get("fixed", {})),
                trailing=StopLossTrailingConfig(**sl_data.get("trailing", {})),
                indicator=StopLossIndicatorConfig(**sl_data.get("indicator", {})),
                break_even=break_even,
            )
        else:
            stop_loss = StopLossConfig()

        trade = TradeRiskConfig(
            sl_tp_mode=trade_data.get("sl_tp_mode", "hybrid"),
            max_loss_pct=trade_data.get("max_loss_pct", 0.02),
            time_limit=trade_data.get("time_limit", 604800),
            atr_period=trade_data.get("atr_period", 14),
            take_profit=take_profit,
            stop_loss=stop_loss,
        )
    else:
        trade = TradeRiskConfig()

    tick_data = risk_dict.get("tick_monitoring", {})
    tick_monitoring = (
        TickMonitoringConfig(
            enabled=tick_data.get("enabled", False),
            tick_type=tick_data.get("tick_type", "trade"),
        )
        if tick_data
        else TickMonitoringConfig()
    )

    return RiskConfig(
        global_risk=global_risk, trade=trade, tick_monitoring=tick_monitoring, raw=raw_dict
    )
