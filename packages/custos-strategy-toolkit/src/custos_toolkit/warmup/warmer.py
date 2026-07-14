"""Indicator warmup service for aligning indicators with external data sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from custos_toolkit.warmup.protocol import SnapshotSupport
from custos_toolkit.warmup.snapshot import IndicatorSnapshot, WarmupConfig


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating warmed indicator values against snapshot."""

    passed: bool
    expected: dict[str, float]
    actual: dict[str, float]
    max_deviation_pct: float
    details: dict[str, float]


@dataclass(frozen=True)
class WarmupResult:
    """Result of indicator warmup operation."""

    success: bool
    mode: str
    bars_processed: int
    snapshot_time: datetime | None
    current_values: dict[str, float]
    validation: ValidationResult | None
    message: str


class IndicatorWarmer:
    """Service for warming up indicators from snapshots."""

    def __init__(
        self,
        config: WarmupConfig,
    ):
        self.config = config

    def _error_result(self, mode: str, message: str) -> WarmupResult:
        """Create a standardized error result to reduce duplication."""
        return WarmupResult(
            success=False,
            mode=mode,
            bars_processed=0,
            snapshot_time=None,
            current_values={},
            validation=None,
            message=message,
        )

    def warm_indicator(
        self,
        indicator: SnapshotSupport,
        indicator_type: str | None = None,
    ) -> WarmupResult:
        """Warm up an indicator based on configuration."""
        if self.config.mode == "none":
            return self._no_warmup()
        elif self.config.mode == "snapshot":
            return self._warm_from_snapshot(indicator, indicator_type)
        elif self.config.mode == "warmup":
            # "warmup" (history-only) is a valid WarmupConfig mode, but it is handled at
            # the strategy level by WarmupManager via nautilus request_bars — not by
            # IndicatorWarmer, which only performs snapshot restore (none/snapshot).
            return self._error_result(
                self.config.mode,
                "warmup mode is handled by WarmupManager (nautilus request_bars), "
                "not IndicatorWarmer; use mode='snapshot' for snapshot restore",
            )
        else:
            return self._error_result(
                self.config.mode,
                f"Unknown warmup mode: {self.config.mode}",
            )

    def _no_warmup(self) -> WarmupResult:
        """Return result for no warmup mode."""
        return WarmupResult(
            success=True,
            mode="none",
            bars_processed=0,
            snapshot_time=None,
            current_values={},
            validation=None,
            message="No warmup performed",
        )

    def _warm_from_snapshot(
        self,
        indicator: SnapshotSupport,
        indicator_type: str | None = None,
    ) -> WarmupResult:
        """Warm indicator from snapshot."""
        snapshot: IndicatorSnapshot | None = None

        if indicator_type and indicator_type in self.config.snapshots:
            snapshot = self.config.snapshots[indicator_type]
        elif self.config.snapshot:
            snapshot = self.config.snapshot

        if snapshot is None:
            return self._error_result(
                "snapshot",
                f"No snapshot found for indicator type: {indicator_type}",
            )

        indicator.load_snapshot(snapshot.values)
        current_values = indicator.export_snapshot()
        validation = self._validate(snapshot.values, current_values)

        return WarmupResult(
            success=True,
            mode="snapshot",
            bars_processed=0,
            snapshot_time=snapshot.timestamp,
            current_values=current_values,
            validation=validation,
            message=f"Loaded snapshot from {snapshot.timestamp}",
        )

    def _validate(
        self,
        expected: dict[str, float],
        actual: dict[str, float],
        tolerance_pct: float = 0.01,
        abs_tolerance: float = 1e-9,
    ) -> ValidationResult:
        """Validate actual values against expected.

        For non-zero expected values, uses relative deviation (percentage).
        For zero expected values, uses absolute tolerance to check if actual
        is also close to zero. This prevents division by zero while still
        validating that zero-valued fields match appropriately.

        Keys in expected but missing in actual are reported as 100% deviation.
        """
        details: dict[str, float] = {}

        for key, exp_val in expected.items():
            if key not in actual:
                # Missing key in actual is treated as 100% deviation
                details[key] = 100.0
            elif exp_val == 0:
                # For zero expected values, check if actual is within absolute tolerance
                # Report deviation as 100% if actual is not close to zero, else 0%
                act_val = actual[key]
                if abs(act_val) <= abs_tolerance:
                    details[key] = 0.0
                else:
                    details[key] = 100.0
            else:
                act_val = actual[key]
                deviation = abs(act_val - exp_val) / abs(exp_val) * 100
                details[key] = deviation

        max_dev = max(details.values()) if details else 0.0
        passed = max_dev <= tolerance_pct * 100

        return ValidationResult(
            passed=passed,
            expected=expected,
            actual=actual,
            max_deviation_pct=max_dev,
            details=details,
        )
