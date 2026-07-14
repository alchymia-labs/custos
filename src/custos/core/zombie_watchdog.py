"""Engine zombie watchdog — autonomous degradation on a stuck engine.

A runner process can stay alive while its execution engine has silently lost its
data / execution connection: orders neither fill nor error, and without the
cloud noticing the deployment looks healthy. The watchdog detects this locally —
no cloud command required (the disconnect-resilient red line) — by tracking how
long an engine has reported disconnected and escalating to a ``degraded`` phase
once a grace window elapses.

The grace window trades a short false-positive risk on transient blips for a
fast live response; a paused spec (maintenance window) is exempt so planned
downtime never trips it. The clock is injectable so the grace logic is tested
without real time.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from custos.core.engine_protocol import ConnectivityState

# Seconds an engine may report disconnected before the watchdog escalates the
# spec to degraded. ~2x a typical reconcile poll — live safety over blip
# tolerance; configurable per deployment.
DEFAULT_GRACE_SECS = 60.0


@dataclass(frozen=True)
class ZombieVerdict:
    """Outcome of one connectivity observation. ``is_zombie`` means the engine
    has been disconnected past the grace window and the instance should degrade."""

    deployment_instance_id: str
    is_zombie: bool
    disconnected_secs: float


class ZombieWatchdog:
    """Per-spec disconnect timer. ``observe`` is called each reconcile tick with
    the latest connectivity; it returns whether the spec has crossed the grace
    threshold. A reconnect or a paused spec clears the timer."""

    def __init__(
        self,
        *,
        grace_secs: float = DEFAULT_GRACE_SECS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._grace_secs = grace_secs
        self._clock = clock
        # deployment_instance_id -> monotonic timestamp first observed disconnected.
        self._degraded_since: dict[str, float] = {}

    @property
    def grace_secs(self) -> float:
        return self._grace_secs

    def forget(self, deployment_instance_id: str) -> None:
        """Remove terminal instance state so a later instance starts cleanly."""
        self._degraded_since.pop(deployment_instance_id, None)

    def observe(
        self,
        deployment_instance_id: str,
        connectivity: ConnectivityState,
        *,
        paused: bool = False,
    ) -> ZombieVerdict:
        now = self._clock()
        connected = connectivity.data_connected and connectivity.exec_connected
        if paused or connected:
            # Healthy again, or intentionally paused — reset the timer so a later
            # disconnect starts a fresh grace window.
            self._degraded_since.pop(deployment_instance_id, None)
            return ZombieVerdict(
                deployment_instance_id=deployment_instance_id,
                is_zombie=False,
                disconnected_secs=0.0,
            )
        since = self._degraded_since.setdefault(deployment_instance_id, now)
        disconnected_secs = now - since
        return ZombieVerdict(
            deployment_instance_id=deployment_instance_id,
            is_zombie=disconnected_secs >= self._grace_secs,
            disconnected_secs=disconnected_secs,
        )
