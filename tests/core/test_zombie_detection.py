"""Engine zombie detection — connectivity probe, grace timer, pause exemption,
and autonomous degraded escalation while the cloud is disconnected (red line 0.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from custos.core.deployment_reconciler import DeploymentReconciler
from custos.core.engine_protocol import ConnectivityState
from custos.core.zombie_watchdog import ZombieWatchdog
from custos.engines.nautilus.host import NoopHost, NtTradingNodeHost


class _Clock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


class _FakeEngine:
    def __init__(self, connected: bool) -> None:
        self._connected = connected

    def check_connected(self) -> bool:
        return self._connected


class _FakeKernel:
    def __init__(self, data_connected: bool, exec_connected: bool) -> None:
        self.data_engine = _FakeEngine(data_connected)
        self.exec_engine = _FakeEngine(exec_connected)


class _FakeNode:
    def __init__(self, data_connected: bool, exec_connected: bool) -> None:
        self.kernel = _FakeKernel(data_connected, exec_connected)


# -- Tier-2 check_engine_connected (host impls) ---------------------------


async def test_check_engine_connected_noophost_connected() -> None:
    state = await NoopHost().check_engine_connected("s-1")
    assert state.data_connected is True
    assert state.exec_connected is True


async def test_check_engine_connected_reports_disconnected() -> None:
    host = NtTradingNodeHost(telemetry_client=None, tenant_id="t", runner_id="r")
    host._active_nodes["s-1"] = (_FakeNode(data_connected=False, exec_connected=False), None)

    state = await host.check_engine_connected("s-1")

    assert state.data_connected is False
    assert state.exec_connected is False


# -- ZombieWatchdog grace / blip / pause state machine --------------------

_DISCONNECTED = ConnectivityState(
    data_connected=False, exec_connected=False, checked_at_epoch_s=0.0
)


def test_zombie_detected_after_grace_period() -> None:
    clock = _Clock(100.0)
    watchdog = ZombieWatchdog(grace_secs=60.0, clock=clock)

    first = watchdog.observe("s-1", _DISCONNECTED)
    assert first.is_zombie is False

    clock.t = 161.0  # 61s disconnected > 60s grace
    escalated = watchdog.observe("s-1", _DISCONNECTED)
    assert escalated.is_zombie is True
    assert escalated.disconnected_secs == 61.0


def test_zombie_not_flagged_during_transient_blip() -> None:
    clock = _Clock(100.0)
    watchdog = ZombieWatchdog(grace_secs=60.0, clock=clock)

    watchdog.observe("s-1", _DISCONNECTED)
    clock.t = 130.0  # 30s < 60s grace
    verdict = watchdog.observe("s-1", _DISCONNECTED)

    assert verdict.is_zombie is False


def test_zombie_exempt_when_paused() -> None:
    clock = _Clock(100.0)
    watchdog = ZombieWatchdog(grace_secs=60.0, clock=clock)

    watchdog.observe("s-1", _DISCONNECTED, paused=False)  # start the timer
    clock.t = 300.0  # long past grace
    verdict = watchdog.observe("s-1", _DISCONNECTED, paused=True)

    # A paused spec (maintenance window) is exempt no matter how long it has
    # been disconnected.
    assert verdict.is_zombie is False


# -- Reconciler autonomous degraded escalation ----------------------------


@dataclass
class _DisconnectedHost:
    deploy_calls: list = field(default_factory=list)

    async def deploy(self, spec: dict, credential: dict) -> str:
        self.deploy_calls.append(spec["spec_id"])
        return f"container-{spec['spec_id']}"

    async def reconfigure(self, spec: dict) -> None: ...

    async def stop(self, spec_id: str) -> None: ...

    def supports_live(self) -> bool:
        return False

    def supports_venue(self, venue: str) -> bool:
        return False

    async def get_open_notional(self, spec_id: str) -> Decimal:
        return Decimal("0")

    async def check_engine_connected(self, spec_id: str) -> ConnectivityState:
        return ConnectivityState(data_connected=False, exec_connected=False, checked_at_epoch_s=0.0)


@dataclass
class _FakeVault:
    def decrypt(self, credential_id: str) -> dict:
        return {"credential_id": credential_id, "permission_scope": "trade_no_withdraw"}


@dataclass
class _FakeNats:
    status_calls: list = field(default_factory=list)

    async def publish_deployment_status(self, *, spec_id: str, payload: dict) -> None:
        self.status_calls.append((spec_id, payload))


def _sandbox_spec() -> dict:
    return {
        "spec_id": "s-1",
        "generation": 1,
        "trading_mode": "sandbox",
        "lifecycle_state": "running",
        "strategy_path": "/opt/strategies/test/strategy.py",
        "provenance_ref": {"credential_id": "cred-s-1"},
        "connector": "binance_perpetual",
        "pairs": ["BTC-USDT"],
        "leverage": 1,
        "sandbox": {"starting_balances": ["10_000 USDT"]},
    }


async def test_zombie_detection_works_when_arx_disconnected() -> None:
    """The watchdog escalates a stuck engine to degraded from purely local
    connectivity checks — no inbound cloud command needed (autonomy = red line
    0.3, disconnect-resilient)."""
    nats = _FakeNats()
    reconciler = DeploymentReconciler(
        nats_client=nats,  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id="runner-7",
        execution_engine=_DisconnectedHost(),
        credential_vault=_FakeVault(),
        zombie_watchdog=ZombieWatchdog(grace_secs=0.0),
    )

    # Deploy a sandbox spec (no cloud round trip beyond this initial spec).
    await reconciler.handle_spec(_sandbox_spec())
    # Then simulate the loop's periodic tick with the cloud silent.
    await reconciler._watchdog_tick()

    degraded = [p for _, p in nats.status_calls if p["phase"] == "degraded"]
    assert len(degraded) == 1
    assert degraded[0]["health_reason"] == "engine_disconnected_zombie"
