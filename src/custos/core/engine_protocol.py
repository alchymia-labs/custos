"""Engine-agnostic execution protocol.

All engine hosts (nautilus / hummingbot / freqtrade / athanor / nt-rust) must
implement ``ExecutionEngineProtocol``.  The G6 gate and the deployment
reconciler operate exclusively through this interface so they remain
engine-agnostic.

``supports_live`` / ``supports_venue`` are synchronous capability queries the
G6 gate calls before any async work; a host declares up-front whether it can
handle live execution and which venues it wires.

Money contract (red line 0.4): every monetary field on every snapshot
dataclass is ``Decimal``. Dataclass frozen annotations alone cannot enforce
runtime types, so a shared ``__post_init__`` helper rejects float mixed into
money fields at construction time.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Protocol, runtime_checkable

# Runtime invariant: every Decimal-declared money field on the snapshot
# dataclasses must be a real ``Decimal`` — a float slipping through breaks
# money math (red line 0.4). Non-money fields (identifier strings, phase
# names, epoch timestamps, integer counters) are outside this set.
_MONEY_FIELDS_SHOULD_BE_DECIMAL = frozenset(
    {
        # PositionSnapshot
        "quantity",
        "avg_px",
        "unrealized_pnl",
        "notional",
        # OrderSnapshot shares ``quantity``; adds ``price``.
        "price",
        # EngineStatus
        "open_notional",
        "peak_equity",
        "current_equity",
        "drawdown_pct",
    }
)


def _reject_float_money(instance: object) -> None:
    """Raise ``TypeError`` if any money field on ``instance`` is not a
    ``Decimal``. Called from every snapshot dataclass's ``__post_init__``."""

    for field in fields(instance):
        if field.name not in _MONEY_FIELDS_SHOULD_BE_DECIMAL:
            continue
        value = getattr(instance, field.name)
        if not isinstance(value, Decimal):
            raise TypeError(
                f"{type(instance).__name__}.{field.name} must be Decimal, "
                f"got {type(value).__name__}"
            )


@dataclass(frozen=True)
class ConnectivityState:
    """Engine connectivity snapshot for the zombie watchdog. ``checked_at_epoch_s``
    is a wall-clock timestamp (not money — float is fine)."""

    data_connected: bool
    exec_connected: bool
    checked_at_epoch_s: float


@dataclass(frozen=True)
class PositionSnapshot:
    """A single open position exposed by ``get_positions``. Every money field is
    ``Decimal``. ``notional`` is gross exposure (``abs(quantity) * avg_px``).
    """

    instrument_id: str
    quantity: Decimal
    avg_px: Decimal
    unrealized_pnl: Decimal
    notional: Decimal

    def __post_init__(self) -> None:  # noqa: D401 — invariant enforcement
        _reject_float_money(self)


@dataclass(frozen=True)
class OrderSnapshot:
    """A single open order exposed by ``get_orders``. ``quantity`` + ``price``
    are ``Decimal``; identifier / side / status remain strings."""

    client_order_id: str
    instrument_id: str
    side: str
    quantity: Decimal
    price: Decimal
    status: str

    def __post_init__(self) -> None:
        _reject_float_money(self)


@dataclass(frozen=True)
class EngineStatus:
    """Engine-side runner state snapshot: aggregate counters + gross exposure +
    equity high-water mark + drawdown percentage.

    The reconciler feeds ``current_equity`` into the fallback breaker so the
    disconnect-resilient drawdown breach is evaluated even while the cloud is
    unreachable. ``peak_equity`` + ``drawdown_pct`` are engine-tracked for
    observability; ``drawdown_pct`` is a percentage (e.g. ``Decimal("20")`` =
    20%).
    """

    phase: str
    position_count: int
    order_count: int
    open_notional: Decimal
    peak_equity: Decimal
    current_equity: Decimal
    drawdown_pct: Decimal

    def __post_init__(self) -> None:
        _reject_float_money(self)


@runtime_checkable
class ExecutionEngineProtocol(Protocol):
    """Engine contract every host must satisfy.

    Tier-1 methods (deploy / reconfigure / stop / capability queries) drive the
    G6 gate and the deployment reconciler.  Tier-2 methods expose runner-level
    risk and connectivity state so the engine-agnostic guards (notional cap,
    fallback breaker, zombie watchdog) can enforce the disconnect-resilient red
    line without knowing the concrete engine.  Every host implements the full
    surface; the ``@runtime_checkable`` isinstance check stays green because
    both shipped hosts add each Tier-2 method in lockstep with the protocol.
    """

    # -- Tier-1: lifecycle + capability ------------------------------------
    async def deploy(self, spec: dict, credential: dict) -> str: ...

    async def reconfigure(self, spec: dict) -> None: ...

    async def stop(self, deployment_instance_id: str) -> None: ...

    def supports_live(self) -> bool: ...

    def supports_venue(self, venue: str) -> bool: ...

    # -- Tier-2: runner-level risk / connectivity state --------------------
    async def get_open_notional(self, deployment_instance_id: str) -> Decimal: ...

    async def check_engine_connected(self, deployment_instance_id: str) -> ConnectivityState: ...

    async def flatten_positions(self, deployment_instance_id: str, reason: str) -> None: ...

    # -- Tier-2: observability snapshot ------------------------------------
    async def get_positions(self, deployment_instance_id: str) -> list[PositionSnapshot]: ...

    async def get_orders(self, deployment_instance_id: str) -> list[OrderSnapshot]: ...

    async def get_engine_status(self, deployment_instance_id: str) -> EngineStatus: ...
