"""Engine-agnostic execution protocol.

All engine hosts (nautilus / hummingbot / freqtrade / athanor / nt-rust) must
implement ``ExecutionEngineProtocol``.  The G6 gate and the deployment
reconciler operate exclusively through this interface so they remain
engine-agnostic.

``supports_live`` / ``supports_venue`` are synchronous capability queries the
G6 gate calls before any async work; a host declares up-front whether it can
handle live execution and which venues it wires.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ConnectivityState:
    """Engine connectivity snapshot for the zombie watchdog. ``checked_at_epoch_s``
    is a wall-clock timestamp (not money — float is fine)."""

    data_connected: bool
    exec_connected: bool
    checked_at_epoch_s: float


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

    async def stop(self, spec_id: str) -> None: ...

    def supports_live(self) -> bool: ...

    def supports_venue(self, venue: str) -> bool: ...

    # -- Tier-2: runner-level risk / connectivity state --------------------
    async def get_open_notional(self, spec_id: str) -> Decimal: ...

    async def check_engine_connected(self, spec_id: str) -> ConnectivityState: ...

    async def flatten_positions(self, spec_id: str, reason: str) -> None: ...
