"""Strategy coordinator components extracted from NautilusTradingStrategy.

Each coordinator owns one slice of the per-bar / lifecycle orchestration and
holds a back-reference to the strategy; they are wired together in
``NautilusTradingStrategy``. This package groups them so the base class stays a
thin orchestrator and the individual slices are easy to locate.
"""

from shared.nautilus.coordinators.config_summary_logger import ConfigSummaryLogger
from shared.nautilus.coordinators.equity_provider import EquityProvider
from shared.nautilus.coordinators.execution import ExecutionCoordinator
from shared.nautilus.coordinators.filter import FilterCoordinator
from shared.nautilus.coordinators.order_reconciler import OrderReconciler
from shared.nautilus.coordinators.pair_context import PairContextCoordinator
from shared.nautilus.coordinators.risk_control import RiskControlCoordinator
from shared.nautilus.coordinators.signal_execution import SignalExecutionCoordinator
from shared.nautilus.coordinators.sizing import SizingCoordinator
from shared.nautilus.coordinators.sltp import SLTPCoordinator
from shared.nautilus.coordinators.snapshot import SnapshotCoordinator
from shared.nautilus.coordinators.startup_validator import StartupValidator
from shared.nautilus.coordinators.trade_event_handler import TradeEventHandler
from shared.nautilus.coordinators.warmup import WarmupCoordinator

__all__ = [
    "ConfigSummaryLogger",
    "EquityProvider",
    "ExecutionCoordinator",
    "FilterCoordinator",
    "OrderReconciler",
    "PairContextCoordinator",
    "RiskControlCoordinator",
    "SignalExecutionCoordinator",
    "SizingCoordinator",
    "SLTPCoordinator",
    "SnapshotCoordinator",
    "StartupValidator",
    "TradeEventHandler",
    "WarmupCoordinator",
]
