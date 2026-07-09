"""
Snapshot configuration for indicator state persistence.

Enables saving indicator state to Redis for fast recovery after restart.
Redis connection is reused from platforms.nautilus.trading_node.database.
"""

import msgspec


class SnapshotConfig(msgspec.Struct, frozen=True):
    """
    Configuration for indicator snapshot persistence.

    Note: Redis connection parameters are taken from
    platforms.nautilus.trading_node.database config.
    Snapshot requires database.enabled=true to function.

    Attributes:
        enabled: Whether snapshot persistence is enabled
        key_prefix: Prefix for Redis keys
        save_interval_bars: Save snapshot every N bars
        save_on_stop: Save snapshot when strategy stops
    """

    enabled: bool = False
    key_prefix: str = "nautilus:snapshot"
    save_interval_bars: int = 100
    save_on_stop: bool = True
    raw: dict | None = None


def build_snapshot_config(
    snapshot_dict: dict | None, raw_dict: dict | None = None
) -> SnapshotConfig:
    """
    Build SnapshotConfig from dictionary.

    Args:
        snapshot_dict: Dictionary with snapshot configuration

    Returns:
        SnapshotConfig instance
    """
    if snapshot_dict is None:
        return SnapshotConfig()

    return SnapshotConfig(
        enabled=snapshot_dict.get("enabled", False),
        key_prefix=snapshot_dict.get("key_prefix", "nautilus:snapshot"),
        save_interval_bars=snapshot_dict.get("save_interval_bars", 100),
        save_on_stop=snapshot_dict.get("save_on_stop", True),
        raw=raw_dict,
    )
