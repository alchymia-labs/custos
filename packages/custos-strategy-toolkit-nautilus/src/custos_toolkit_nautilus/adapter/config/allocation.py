"""
Capital allocation configuration for multi-pair strategies.

Provides configuration for tiered capital allocation across trading pairs.
"""

import msgspec


class AllocationConfig(msgspec.Struct, frozen=True):
    """
    Capital allocation configuration.

    Attributes:
        mode: Allocation mode - "tiered" (pre-defined ratios), "equal" (even split),
            "dynamic"
        tiers: Pair to allocation ratio mapping (e.g., {"BTC-USDT": 0.5})
        max_total_exposure: Maximum total portfolio exposure (0-1)
        rebalance_threshold: Threshold for triggering rebalance (e.g., 0.05 = 5%)
    """

    mode: str = "tiered"
    tiers: dict[str, float] = {}
    max_total_exposure: float = 0.8
    rebalance_threshold: float = 0.05


def build_allocation_config(data: dict | None) -> AllocationConfig:
    """
    Build AllocationConfig from dictionary.

    Args:
        data: Configuration dictionary or None

    Returns:
        AllocationConfig instance
    """
    if not data:
        return AllocationConfig()

    return AllocationConfig(
        mode=data.get("mode", "tiered"),
        tiers=data.get("tiers", {}),
        max_total_exposure=data.get("max_total_exposure", 0.8),
        rebalance_threshold=data.get("rebalance_threshold", 0.05),
    )
