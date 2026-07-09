"""Data classes for indicator warmup configuration and snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal


@dataclass(frozen=True)
class IndicatorSnapshot:
    """
    Snapshot of an indicator's state at a specific point in time.
    """

    indicator_type: str
    timestamp: datetime
    values: dict[str, float]


@dataclass(frozen=True)
class CheckpointValue:
    """
    Expected indicator value at a checkpoint.

    Attributes:
        value: Expected indicator value (e.g., SuperTrend line price)
        trend: Expected trend direction (optional, for trend indicators)
    """

    value: float
    trend: int | None = None


@dataclass(frozen=True)
class PriceSnapshot:
    """
    Expected OHLCV price data at a checkpoint.

    Attributes:
        open: Expected open price
        high: Expected high price
        low: Expected low price
        close: Expected close price
        volume: Expected volume (optional)
    """

    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


@dataclass(frozen=True)
class Checkpoint:
    """
    A single checkpoint for post-restore validation.

    Attributes:
        offset_bars: Number of bars after snapshot restore
        bar_close_time: Expected bar close time for validation
        indicators: Expected indicator values keyed by indicator name
        price: Expected OHLCV price data (optional, for price validation)
    """

    offset_bars: int
    bar_close_time: datetime
    indicators: dict[str, CheckpointValue]
    price: PriceSnapshot | None = None


@dataclass(frozen=True)
class CheckpointConfig:
    """
    Configuration for checkpoint validation.

    Attributes:
        tolerance_pct: Allowed percentage difference for value validation
        trend_strict: Whether trend must match exactly
        points: List of checkpoints to validate
    """

    tolerance_pct: float = 0.1
    trend_strict: bool = True
    points: list[Checkpoint] = field(default_factory=list)


@dataclass(frozen=True)
class WarmupConfig:
    """
    Configuration for indicator warmup.

    Attributes:
        mode: Warmup mode - "none", "snapshot" (snapshot restore via IndicatorWarmer),
            or "warmup" (history-only; handled at strategy level by WarmupManager via
            nautilus request_bars, not by IndicatorWarmer)
        snapshot: Single indicator snapshot (deprecated, use snapshots)
        snapshots: Dictionary of indicator snapshots by type
        min_bars: Minimum bars to request for warmup
        preferred_bars: Preferred bars to request when no snapshot available
        timeout_secs: Timeout for historical data request
        checkpoints: Optional checkpoint validation config
    """

    mode: Literal["snapshot", "warmup", "none"] = "none"
    snapshot: IndicatorSnapshot | None = None
    snapshots: dict[str, IndicatorSnapshot] = field(default_factory=dict)
    min_bars: int = 500
    preferred_bars: int = 2000
    timeout_secs: int = 30
    checkpoints: CheckpointConfig | None = None


def _extract_value(val):
    """
    Extract value from potentially nested config format.

    Handles both:
    - Direct values: "1-HOUR" -> "1-HOUR"
    - Schema format: {"value": "1-HOUR", ...} -> "1-HOUR"
    """
    if isinstance(val, dict) and "value" in val:
        return val["value"]
    return val


def _parse_timestamp(timestamp_raw: str) -> datetime:
    """Parse ISO format timestamp string to datetime."""
    timestamp_str = _extract_value(timestamp_raw) if timestamp_raw else ""
    if timestamp_str:
        if timestamp_str.endswith("Z"):
            timestamp_str = timestamp_str[:-1] + "+00:00"
        return datetime.fromisoformat(timestamp_str)
    return datetime.now(UTC)


def _parse_checkpoints(checkpoint_config: dict) -> CheckpointConfig | None:
    """Parse checkpoint configuration from dict."""
    if not checkpoint_config:
        return None

    tolerance_pct = float(_extract_value(checkpoint_config.get("tolerance_pct", 0.1)))
    trend_strict = bool(_extract_value(checkpoint_config.get("trend_strict", True)))

    points_raw = checkpoint_config.get("points", [])
    points: list[Checkpoint] = []

    for point_raw in points_raw:
        offset_bars = int(_extract_value(point_raw.get("offset_bars", 0)))
        bar_close_time = _parse_timestamp(point_raw.get("bar_close_time", ""))

        # Parse price snapshot if present
        price = None
        price_raw = point_raw.get("price")
        if price_raw and isinstance(price_raw, dict):
            price = PriceSnapshot(
                open=float(_extract_value(price_raw.get("open", 0))),
                high=float(_extract_value(price_raw.get("high", 0))),
                low=float(_extract_value(price_raw.get("low", 0))),
                close=float(_extract_value(price_raw.get("close", 0))),
                volume=float(_extract_value(price_raw.get("volume")))
                if price_raw.get("volume")
                else None,
            )

        indicators: dict[str, CheckpointValue] = {}
        for name, values in point_raw.items():
            if name in ("offset_bars", "bar_close_time", "price"):
                continue
            if isinstance(values, dict):
                value = float(_extract_value(values.get("value", 0)))
                trend_raw = values.get("trend")
                trend = int(_extract_value(trend_raw)) if trend_raw is not None else None
                indicators[name] = CheckpointValue(value=value, trend=trend)

        points.append(
            Checkpoint(
                offset_bars=offset_bars,
                bar_close_time=bar_close_time,
                indicators=indicators,
                price=price,
            )
        )

    return CheckpointConfig(
        tolerance_pct=tolerance_pct,
        trend_strict=trend_strict,
        points=points,
    )


def warmup_config_from_dict(config_dict: dict) -> WarmupConfig:
    """
    Create WarmupConfig from a dictionary (e.g., from YAML config).

    Handles both direct values and schema format where values are wrapped
    in {"value": ...} dictionaries.
    """
    mode = _extract_value(config_dict.get("mode", "none"))
    history = config_dict.get("history", {})
    min_bars = _extract_value(history.get("min_bars", 500))
    preferred_bars = _extract_value(history.get("preferred_bars", 2000))
    timeout_secs = _extract_value(history.get("timeout_secs", 30))

    snapshots: dict[str, IndicatorSnapshot] = {}
    snapshot_config = config_dict.get("snapshot", {})

    if snapshot_config:
        timestamp = _parse_timestamp(snapshot_config.get("timestamp", ""))

        indicators = snapshot_config.get("indicators", {})
        for indicator_type, values in indicators.items():
            # Extract values, handling nested {value: ...} format
            float_values = {}
            for k, v in values.items():
                extracted = _extract_value(v)
                float_values[k] = float(extracted)
            snapshots[indicator_type] = IndicatorSnapshot(
                indicator_type=indicator_type,
                timestamp=timestamp,
                values=float_values,
            )

    snapshot = list(snapshots.values())[0] if snapshots else None

    # Parse checkpoints from snapshot config
    checkpoints = _parse_checkpoints(snapshot_config.get("checkpoints"))

    return WarmupConfig(
        mode=mode,
        snapshot=snapshot,
        snapshots=snapshots,
        min_bars=min_bars,
        preferred_bars=preferred_bars,
        timeout_secs=timeout_secs,
        checkpoints=checkpoints,
    )
