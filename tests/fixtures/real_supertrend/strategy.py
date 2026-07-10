"""
SuperTrend Strategy for NautilusTrader

ATR-based trend following strategy using dynamic support/resistance lines.
Uses shared modules for platform-agnostic calculations.
Configuration loaded from config.yaml with base_config.yaml merging.

This strategy extends NautilusTradingStrategy and only implements:
- Strategy-specific indicator initialization (SuperTrend)
- Signal generation logic (calculate_signal)

All common functionality (filters, risk management, position management,
execution, SL/TP) is inherited from the base class.
"""

import msgspec
from nautilus_trader.model.data import Bar
from shared.config import ConfigWrapper
from shared.nautilus import (
    NautilusTradingStrategy,
    NautilusTradingStrategyConfig,
    PairContext,
    register_strategy,
)
from shared.nautilus.indicators import SuperTrend
from shared.signals import Signal


# =============================================================================
# Strategy-Specific Parameters Config
# =============================================================================
class SuperTrendParametersConfig(msgspec.Struct, frozen=True):
    """SuperTrend strategy parameters (from config.yaml parameters.*)."""

    atr_period: int = 10
    atr_multiplier: float = 3.0


def build_parameters_config(config_wrapper: ConfigWrapper) -> SuperTrendParametersConfig:
    """Build SuperTrendParametersConfig from ConfigWrapper."""
    params = config_wrapper.parameters
    if not params:
        return SuperTrendParametersConfig()
    return SuperTrendParametersConfig(
        atr_period=params.get("atr_period", 10),
        atr_multiplier=params.get("atr_multiplier", 3.0),
    )


# =============================================================================
# NautilusTrader Strategy Configuration
# =============================================================================
class SuperTrendStrategyConfig(NautilusTradingStrategyConfig, frozen=True):
    """
    Configuration for SuperTrend strategy.

    Extends NautilusTradingStrategyConfig with strategy-specific parameters.
    Common sections (trading, position, risk, filters, platforms, backtesting)
    are inherited from the base class.

    Note: instrument_id and bar_type are derived at runtime from
    config.trading and config.platforms, not passed explicitly.
    """

    # Strategy-Specific Parameters
    parameters: SuperTrendParametersConfig = SuperTrendParametersConfig()


# =============================================================================
# Strategy Implementation
# =============================================================================
class SuperTrendStrategy(NautilusTradingStrategy):
    """
    SuperTrend Strategy Implementation.

    Extends NautilusTradingStrategy with SuperTrend-specific signal generation.
    A trend-following strategy that uses the SuperTrend indicator to generate
    buy and sell signals based on trend reversals.

    Entry Logic:
    - Long: When trend changes from bearish to bullish
    - Short: When trend changes from bullish to bearish

    Exit Logic (handled by base class or explicit signal):
    - Close long on bearish trend reversal
    - Close short on bullish trend reversal

    All common functionality is inherited from NautilusTradingStrategy:
    - Filter initialization and checking (ADX, volatility, volume, time)
    - Risk management (daily loss, drawdown, consecutive losses)
    - Position management (sizing, limits)
    - Execution (market/limit orders)
    - Stop loss / take profit
    """

    def __init__(self, config: SuperTrendStrategyConfig) -> None:
        """Initialize the SuperTrend strategy."""
        super().__init__(config)

        # Indicator logging (for backtest visualization)
        self._log_indicators = config.backtesting.log_indicators
        self._indicator_history: dict | None = None
        if self._log_indicators:
            self._indicator_history = {
                "supertrend": {
                    "type": "SUPERTREND",
                    "config": {
                        "atr_period": config.parameters.atr_period,
                        "multiplier": config.parameters.atr_multiplier,
                    },
                    "points": [],
                },
            }

        # SuperTrend indicator (initialized in on_strategy_start)
        self.supertrend: SuperTrend | None = None

        # State for trend reversal detection
        self._prev_trend: int = 0

        # Primary pair for single-pair strategy (set in on_strategy_start)
        self._primary_pair: str = ""

    # =========================================================================
    # SINGLE-PAIR COMPATIBILITY HELPERS
    # =========================================================================

    @property
    def _instrument_id(self):
        """Get instrument ID for primary pair (single-pair compatibility)."""
        return self._get_context(self._primary_pair).instrument_id

    @property
    def _bar_type(self):
        """Get bar type for primary pair (single-pair compatibility)."""
        return self._get_context(self._primary_pair).bar_type

    # =========================================================================
    # HOOK METHOD IMPLEMENTATIONS
    # =========================================================================

    def on_strategy_start(self) -> None:
        """Initialize SuperTrend indicator."""
        # Set primary pair for single-pair compatibility
        self._primary_pair = self.config.trading.pairs[0]

        # Initialize SuperTrend indicator
        self.supertrend = SuperTrend(
            length=self.config.parameters.atr_period,
            multiplier=self.config.parameters.atr_multiplier,
        )

        # Register indicator for automatic bar updates
        self.register_indicator_for_bars(self._bar_type, self.supertrend)

        # Expose the indicator on the pair context so the framework on_save/on_load
        # (Redis) state path persists/restores its state (it iterates ctx.indicators).
        self._get_context(self._primary_pair).indicators["supertrend"] = self.supertrend

        self.log.info(
            f"SuperTrend indicator initialized: "
            f"ATR({self.config.parameters.atr_period}), "
            f"Multiplier({self.config.parameters.atr_multiplier})"
        )

    def on_strategy_stop(self) -> None:
        """Clean up strategy resources."""
        self.cancel_all_orders(self._instrument_id)
        self.log.info("SuperTrend strategy stopped")

    def on_warmup_complete(self) -> None:
        """Log warmup completion once. Note: _prev_trend stays 0 to enable startup entry."""
        # Must call super(): writing the ready-signal file is base-class behavior.
        # Skipping it leaves sidecar readiness=False, so financial metrics are never
        # collected and KPIs stay empty.
        super().on_warmup_complete()
        # Only log once when indicator first becomes initialized
        if (
            not hasattr(self, "_warmup_logged")
            and self.supertrend is not None
            and self.supertrend.initialized
        ):
            self._warmup_logged = True
            self.log.info(
                f"SuperTrend warmup complete: trend={self.supertrend.trend}, "
                f"_prev_trend={self._prev_trend} (will enable startup entry)"
            )

    def calculate_signal(self, ctx: PairContext, bar: Bar) -> Signal:
        """
        Calculate trading signal based on SuperTrend indicator.

        Emits entry/exit signals from trend direction and position state. Entries are
        not pre-sized -- the base pipeline sizes them after the entry gate so filter
        size factors apply. A trend flip against an open position emits an exit (which
        bypasses the entry gate) rather than a reversal entry.

        Args:
            ctx: PairContext (has .pair / .instrument_id)
            bar: Current bar data

        Returns:
            Signal object with direction and amount
        """
        if self.supertrend is None:
            self.log.error("SuperTrend indicator is None - strategy cannot function")
            return Signal.neutral(bar.close, pair=ctx.pair)

        if not self.supertrend.initialized:
            # Normal warmup period - only log once when count changes significantly
            return Signal.neutral(bar.close, pair=ctx.pair)

        current_trend = self.supertrend.trend
        trading = self.config.trading

        # Detect trend reversals
        trend_up = current_trend == 1 and self._prev_trend == -1
        trend_down = current_trend == -1 and self._prev_trend == 1

        # Startup entry: when _prev_trend is 0 (first signal after warmup),
        # enter established trend if flat. This fixes the issue where strategy
        # would miss entry if started during an ongoing trend.
        is_startup = self._prev_trend == 0 and current_trend != 0

        # Store metadata for logging
        metadata = {
            "supertrend": self.supertrend.value,
            "trend": current_trend,
            "prev_trend": self._prev_trend,
        }

        # Trend flipped against an open position: close it first. Exits bypass the entry
        # gate (filters / risk), so a blocked re-entry can never leave the position
        # exposed against the new trend. Closing fires regardless of enable_long/short.
        # Re-entry in the new direction is gated normally on a later (flat) bar.
        if trend_up and self.portfolio.is_net_short(self._instrument_id):
            return Signal.exit_short(
                bar.close, pair=ctx.pair, action="close_on_reversal", **metadata
            )
        if trend_down and self.portfolio.is_net_long(self._instrument_id):
            return Signal.exit_long(
                bar.close, pair=ctx.pair, action="close_on_reversal", **metadata
            )

        # Entry when flat (startup or on a fresh reversal). NOT pre-sized -- _process_bar
        # sizes after the entry gate, so filter size_factor / reduce_size actually apply.
        if self.portfolio.is_flat(self._instrument_id) and (is_startup or trend_up or trend_down):
            if current_trend == 1 and trading.enable_long:
                action = "startup_long" if is_startup else "enter_long"
                return Signal.enter_long(bar.close, pair=ctx.pair, action=action, **metadata)
            if current_trend == -1 and trading.enable_short:
                action = "startup_short" if is_startup else "enter_short"
                return Signal.enter_short(bar.close, pair=ctx.pair, action=action, **metadata)

        # NEUTRAL signal also includes trend metadata for observability
        return Signal.neutral(bar.close, pair=ctx.pair, **metadata)

    def on_post_bar(self, ctx: PairContext, bar: Bar) -> None:
        """Post-bar processing: update state and log indicators.

        Args:
            ctx: PairContext (single-pair strategy does not use pair)
            bar: Current bar data
        """
        if self.supertrend is None:
            # Error already logged in calculate_signal
            return

        if not self.supertrend.initialized:
            return

        current_trend = self.supertrend.trend

        # Log indicator values for backtest visualization
        if self._log_indicators and self._indicator_history is not None:
            self._indicator_history["supertrend"]["points"].append(
                {
                    "time": bar.ts_event // 1_000_000_000,
                    "value": float(self.supertrend.value),
                    "direction": current_trend,
                }
            )

        # Commit the trend to _prev_trend only once the entry it warrants is in flight
        # or done (position reflects it / an entry order is pending), or its direction
        # isn't tradeable. While a filter or risk gate blocks the entry (nothing pending,
        # position flat/opposite) _prev_trend is held so the reversal/startup entry is
        # re-detected next bar instead of being permanently swallowed.
        if current_trend == 0 or self._trend_committed(ctx, current_trend):
            self._prev_trend = current_trend

        # Log status
        self._log_status(bar, current_trend)

    def _trend_committed(self, ctx: PairContext, trend: int) -> bool:
        """Whether the current trend should be committed to _prev_trend: an entry order
        *toward this trend* is pending (submitted, awaiting fill), the position already
        reflects it, or its direction isn't tradeable. Only an un-acted tradeable trend
        (gate-blocked, nothing pending toward it) is held back so the entry is
        re-attempted next bar. A stale opposite-direction pending entry does not count."""
        if ctx.order_tracker.entry_order_id is not None and ctx.order_tracker.entry_side == trend:
            return True
        trading = self.config.trading
        if trend == 1:
            return self.portfolio.is_net_long(self._instrument_id) or not trading.enable_long
        if trend == -1:
            return self.portfolio.is_net_short(self._instrument_id) or not trading.enable_short
        return True

    # =========================================================================
    # SNAPSHOT PERSISTENCE
    # =========================================================================

    def get_snapshot_indicators(self) -> dict:
        """Return indicators to snapshot."""
        if self.supertrend is not None:
            return {"supertrend": self.supertrend}
        return {}

    def get_snapshot_state(self) -> dict:
        """Return strategy-specific state to snapshot."""
        return {"prev_trend": self._prev_trend}

    def restore_from_snapshot(self, snapshot: dict) -> bool:
        """Restore strategy state from snapshot."""
        try:
            # Restore indicator
            indicators = snapshot.get("indicators", {})
            if "supertrend" in indicators and self.supertrend is not None:
                self.supertrend.from_snapshot(indicators["supertrend"])
                self.log.info(
                    f"SuperTrend restored: trend={self.supertrend.trend}, "
                    f"value={self.supertrend.value:.2f}"
                )

            # Restore strategy state
            state = snapshot.get("state", {})
            self._prev_trend = state.get("prev_trend", 0)
            self.log.info(f"Strategy state restored: prev_trend={self._prev_trend}")

            return True
        except Exception as e:
            self.log.warning(f"Snapshot restore failed: {e}")
            return False

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _log_status(self, bar: Bar, trend: int) -> None:
        """Log current strategy status."""
        trend_map = {1: "BULL", -1: "BEAR", 0: "NEUTRAL"}
        trend_str = trend_map.get(trend, "NEUTRAL")

        if self.portfolio.is_flat(self._instrument_id):
            pos_str = "FLAT"
        elif self.portfolio.is_net_long(self._instrument_id):
            pos_str = "LONG"
        else:
            pos_str = "SHORT"

        # Log trend and position status (useful for production monitoring)
        self.log.info(f"Status: trend={trend_str} | ST={self.supertrend.value:.2f} | pos={pos_str}")

    def on_reset(self) -> None:
        """Reset the strategy state."""
        if self.supertrend is not None:
            self.supertrend.reset()
        self._prev_trend = 0

    def get_indicator_history(self) -> dict:
        """
        Get indicator history for backtest visualization.

        Returns
        -------
        dict
            Dictionary containing indicator data
        """
        return self._indicator_history or {}


# =============================================================================
# Register Strategy with Factory
# =============================================================================
register_strategy(
    name="supertrend",
    strategy_class=SuperTrendStrategy,
    config_class=SuperTrendStrategyConfig,
    parameters_builder=build_parameters_config,
)


def create_strategy(config: dict) -> SuperTrendStrategy:
    """Crucible entry-point factory (alephain.strategies group).

    Implements the Crucible StrategyFactory protocol: receives the raw
    config.yaml dict (with any overrides already applied) and returns a
    configured strategy instance. Base defaults are merged the same way
    as shared.config.load_config().
    """
    from pathlib import Path

    from shared.config import deep_merge, load_yaml_file
    from shared.config import loader as _config_loader
    from shared.nautilus import create_strategy as _create_registered_strategy

    base_path = Path(_config_loader.__file__).parent / "base_config.yaml"
    base_config = load_yaml_file(base_path) if base_path.exists() else {}
    wrapper = ConfigWrapper(deep_merge(base_config, config))
    return _create_registered_strategy("supertrend", config_wrapper=wrapper)
