# shared/filters/time_filter.py
"""
Time-based trading filter.

Filters trades by time-of-day window and weekday, at minute granularity.

Keeps the ``_filter`` suffix (rest of the package uses bare names): a bare
``time.py`` would shadow the stdlib ``time`` module on local imports.
"""

from datetime import UTC, datetime
from typing import cast

from ..config._values import config_value
from ..protocols.bar import BarProtocol
from ..protocols.filter import FilterResult
from .base import BaseFilter
from .registry import register_filter

# Sentinel meaning "trade all day" — skips the hour-window check entirely so the
# inclusive 23:59 boundary never wrongly excludes the final minute of the day.
_FULL_DAY = "00:00-23:59"


def parse_trading_hours(trading_hours: str) -> tuple[int, int]:
    """
    Parse a trading hours string into start and end minutes from midnight.

    Args:
        trading_hours: Trading hours in "HH:MM-HH:MM" format (UTC)

    Returns:
        Tuple of (start_minutes, end_minutes) from midnight

    Raises:
        ValueError: If the format is invalid or any clock value is out of range
            (hour 0-23, minute 0-59)

    Example:
        >>> parse_trading_hours("09:00-17:00")
        (540, 1020)
        >>> parse_trading_hours("22:00-06:00")  # Overnight
        (1320, 360)
    """
    if not isinstance(trading_hours, str):
        raise ValueError(f"trading_hours must be a string, got {type(trading_hours).__name__}")
    start_str, end_str = trading_hours.split("-")
    start_hour, start_min = map(int, start_str.split(":"))
    end_hour, end_min = map(int, end_str.split(":"))
    for hour, minute in ((start_hour, start_min), (end_hour, end_min)):
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"invalid clock value in trading_hours: {trading_hours!r}")
    return start_hour * 60 + start_min, end_hour * 60 + end_min


@register_filter("time")
class TimeFilter(BaseFilter):
    """
    Filter trades by time-of-day window and weekday (minute granularity, UTC).

    Config options:
        enabled: bool - Whether the filter is active
        trading_hours: str - "HH:MM-HH:MM" window; "00:00-23:59" means all day
        excluded_days: list[int] - Blocked weekdays (0=Mon, 6=Sun)
        excluded_dates: list[str] - Blocked calendar dates (YYYY-MM-DD)
    """

    @property
    def name(self) -> str:
        return "time"

    def __init__(self, config: dict[str, object]):
        super().__init__(config)
        self.enabled = config_value(config, "enabled", True)
        self.trading_hours = config_value(config, "trading_hours", _FULL_DAY)
        self.excluded_days = set(cast(list[int], config.get("excluded_days") or []))
        self.excluded_dates = set(cast(list[str], config.get("excluded_dates") or []))
        # Parse eagerly so a malformed window fails fast at construction rather than
        # silently allowing every trade at runtime. None means "all day, no gating".
        if self.trading_hours == _FULL_DAY:
            self._window: tuple[int, int] | None = None
        else:
            self._window = parse_trading_hours(self.trading_hours)
        self._ready = True  # No warmup needed

    def update(self, bar: BarProtocol) -> None:
        """Time filter doesn't need state updates."""
        pass

    def check(self, bar: BarProtocol) -> FilterResult:
        """Check if the bar's timestamp falls within the allowed trading window."""
        if not self.enabled:
            return FilterResult.allow()

        dt = datetime.fromtimestamp(bar.timestamp / 1e9, tz=UTC)

        if dt.weekday() in self.excluded_days:
            return FilterResult.block(f"Day {dt.weekday()} is excluded")

        date_str = dt.strftime("%Y-%m-%d")
        if date_str in self.excluded_dates:
            return FilterResult.block(f"Date {date_str} is excluded")

        if self._window is not None:
            start_min, end_min = self._window
            current_min = dt.hour * 60 + dt.minute
            if start_min <= end_min:
                in_window = start_min <= current_min <= end_min
            else:
                # Overnight window (e.g., 22:00-06:00) wraps past midnight.
                in_window = current_min >= start_min or current_min <= end_min
            if not in_window:
                return FilterResult.block(
                    f"Time {dt.hour:02d}:{dt.minute:02d} outside {self.trading_hours}"
                )

        return FilterResult.allow()
