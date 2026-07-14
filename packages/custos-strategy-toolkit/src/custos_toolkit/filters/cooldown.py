# shared/filters/cooldown.py
"""
Cooldown period filter.
Enforces minimum time between trades after exits.
"""

from ..config._values import config_value
from ..protocols.bar import BarProtocol
from ..protocols.filter import FilterResult
from .base import BaseFilter
from .registry import register_filter


@register_filter("cooldown")
class CooldownFilter(BaseFilter):
    """
    Enforce cooldown period after trade exits.

    Config options:
        enabled: bool - Whether filter is active
        after_exit: int - Seconds to wait after any exit
        after_stop_loss: int - Seconds to wait after stop loss
        after_take_profit: int - Seconds to wait after take profit
    """

    @property
    def name(self) -> str:
        return "cooldown"

    def __init__(self, config: dict[str, object]):
        super().__init__(config)
        self.enabled = config_value(config, "enabled", True)
        self.after_exit = config_value(config, "after_exit", 60)
        self.after_stop_loss = config_value(config, "after_stop_loss", 300)
        self.after_take_profit = config_value(config, "after_take_profit", 0)

        # State
        self._last_exit_time: float = 0
        self._last_exit_type: str = ""
        self._ready = True

    def update(self, bar: BarProtocol) -> None:
        """Cooldown filter state is updated via record_exit()."""
        pass

    def check(self, bar: BarProtocol) -> FilterResult:
        """Check if cooldown period has passed."""
        if not self.enabled:
            return FilterResult.allow()

        if self._last_exit_time == 0:
            return FilterResult.allow()

        current_ts = bar.timestamp / 1e9  # Convert to seconds
        elapsed = current_ts - self._last_exit_time

        # Determine required cooldown based on exit type
        if self._last_exit_type == "stop_loss":
            required = self.after_stop_loss
        elif self._last_exit_type == "take_profit":
            required = self.after_take_profit
        else:
            required = self.after_exit

        if elapsed < required:
            remaining = required - elapsed
            return FilterResult.block(
                f"Cooldown: {remaining:.0f}s remaining after {self._last_exit_type}"
            )

        return FilterResult.allow()

    def record_exit(self, timestamp: int, exit_type: str = "exit") -> None:
        """
        Record an exit for cooldown tracking.

        Args:
            timestamp: Exit timestamp in nanoseconds
            exit_type: Type of exit ("stop_loss", "take_profit", or other)
        """
        self._last_exit_time = timestamp / 1e9  # Store in seconds
        self._last_exit_type = exit_type

    def reset(self) -> None:
        """Reset cooldown state."""
        self._last_exit_time = 0
        self._last_exit_type = ""
