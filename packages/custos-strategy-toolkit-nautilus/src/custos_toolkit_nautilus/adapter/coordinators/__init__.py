"""Strategy coordinator components extracted from NautilusTradingStrategy.

Each coordinator owns one slice of the per-bar / lifecycle orchestration and
holds a back-reference to the strategy; they are wired together in
``NautilusTradingStrategy``. This package groups them so the base class stays a
thin orchestrator and the individual slices are easy to locate.
"""

from custos_toolkit_nautilus.adapter.coordinators.config_summary_logger import ConfigSummaryLogger
from custos_toolkit_nautilus.adapter.coordinators.equity_provider import EquityProvider
from custos_toolkit_nautilus.adapter.coordinators.execution import ExecutionCoordinator
from custos_toolkit_nautilus.adapter.coordinators.filter import FilterCoordinator
from custos_toolkit_nautilus.adapter.coordinators.order_reconciler import OrderReconciler
from custos_toolkit_nautilus.adapter.coordinators.pair_context import PairContextCoordinator
from custos_toolkit_nautilus.adapter.coordinators.risk_control import RiskControlCoordinator
from custos_toolkit_nautilus.adapter.coordinators.signal_execution import SignalExecutionCoordinator
from custos_toolkit_nautilus.adapter.coordinators.sizing import SizingCoordinator
from custos_toolkit_nautilus.adapter.coordinators.sltp import SLTPCoordinator
from custos_toolkit_nautilus.adapter.coordinators.snapshot import SnapshotCoordinator
from custos_toolkit_nautilus.adapter.coordinators.startup_validator import StartupValidator
from custos_toolkit_nautilus.adapter.coordinators.trade_event_handler import TradeEventHandler
from custos_toolkit_nautilus.adapter.coordinators.warmup import WarmupCoordinator

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
