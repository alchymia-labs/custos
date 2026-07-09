"""Protocol definitions for indicator warmup support."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class SnapshotSupport(Protocol):
    """
    Protocol for indicators that support snapshot-based initialization.

    Indicators implementing this protocol can:
    1. Load state from a snapshot (e.g., from TradingView)
    2. Export current state as a snapshot (for verification)
    """

    def load_snapshot(self, values: dict[str, float]) -> None:
        """Load indicator state from a snapshot."""
        ...

    def export_snapshot(self) -> dict[str, float]:
        """Export current indicator state as a snapshot."""
        ...
