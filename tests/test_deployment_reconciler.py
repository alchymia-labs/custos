"""DeploymentReconciler — generation idempotency + drift + disconnect safety.

Test coverage follows plan-index §6 + Plan 06 reconcile contract:
- generation diff → trigger reconcile (deploy call)
- same generation → no-op (idempotent)
- older generation → stale reject, no host redeploy
- drift_strikes increments (NautilusHost continuous failures → DriftDetected)
- status report: publish_deployment_status includes correct observed_generation
- disconnect safety (CLAUDE.md red line): when NATS publish fails, reconcile
  loop still advances local state and host calls continue.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from custos.core.deployment_reconciler import DeploymentReconciler


@dataclass
class _FakeHost:
    deploy_calls: list[tuple[dict, dict]] = field(default_factory=list)
    reconfigure_calls: list[dict] = field(default_factory=list)
    stop_calls: list[str] = field(default_factory=list)
    deploy_raises: bool = False

    async def deploy(self, spec: dict, credential: dict) -> str:
        self.deploy_calls.append((spec, credential))
        if self.deploy_raises:
            raise RuntimeError("nautilus deploy failed")
        return f"container-{spec['spec_id']}"

    async def reconfigure(self, spec: dict) -> None:
        self.reconfigure_calls.append(spec)

    async def stop(self, spec_id: str) -> None:
        self.stop_calls.append(spec_id)


@dataclass
class _FakeVault:
    decrypt_calls: list[str] = field(default_factory=list)

    def decrypt(self, credential_id: str) -> dict:
        self.decrypt_calls.append(credential_id)
        return {
            "credential_id": credential_id,
            "tenant_id": "acme",
            "permission_scope": "trade_no_withdraw",
            "secret": "<fake>",
        }


@dataclass
class _FakeNats:
    tenant_id: str = "acme"
    runner_id: str = "runner-7"
    status_calls: list[tuple[str, dict]] = field(default_factory=list)
    publish_raises: bool = False

    async def subscribe_deployment_spec(self, *, strategy_id: str):  # pragma: no cover
        raise NotImplementedError("not used in unit tests")

    async def publish_deployment_status(self, *, spec_id: str, payload: dict) -> None:
        if self.publish_raises:
            raise RuntimeError("nats disconnected")
        self.status_calls.append((spec_id, payload))


def _make_reconciler(host=None, vault=None, nats=None) -> DeploymentReconciler:
    return DeploymentReconciler(
        nats_client=nats or _FakeNats(),  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id="runner-7",
        execution_engine=host or _FakeHost(),
        credential_vault=vault or _FakeVault(),
        drift_threshold=3,
    )


def _spec(spec_id: str, generation: int, lifecycle: str = "running") -> dict:
    return {
        "spec_id": spec_id,
        "generation": generation,
        "trading_mode": "sandbox",
        "lifecycle_state": lifecycle,
        "strategy_path": "/opt/strategies/test/strategy.py",
        "provenance_ref": {"credential_id": f"cred-{spec_id}"},
        "connector": "binance_perpetual",
        "pairs": ["BTC-USDT"],
        "leverage": 1,
        "sandbox": {"starting_balances": ["10_000 USDT"]},
    }


@pytest.mark.asyncio
async def test_generation_diff_triggers_deploy() -> None:
    host = _FakeHost()
    nats = _FakeNats()
    reconciler = _make_reconciler(host=host, nats=nats)

    await reconciler.handle_spec(_spec("s-1", generation=2))

    assert len(host.deploy_calls) == 1
    assert host.deploy_calls[0][0]["generation"] == 2
    assert len(nats.status_calls) == 1
    assert nats.status_calls[0][1]["observed_generation"] == 2
    assert nats.status_calls[0][1]["phase"] == "running"


@pytest.mark.asyncio
async def test_same_generation_is_noop() -> None:
    host = _FakeHost()
    reconciler = _make_reconciler(host=host)

    await reconciler.handle_spec(_spec("s-1", generation=2))
    await reconciler.handle_spec(_spec("s-1", generation=2))

    # only one deploy call — second arrival is no-op
    assert len(host.deploy_calls) == 1
    assert len(host.reconfigure_calls) == 0


@pytest.mark.asyncio
async def test_stale_generation_rejected() -> None:
    host = _FakeHost()
    reconciler = _make_reconciler(host=host)

    await reconciler.handle_spec(_spec("s-1", generation=5))
    # arrive late with old generation
    await reconciler.handle_spec(_spec("s-1", generation=3))

    assert len(host.deploy_calls) == 1
    assert len(host.reconfigure_calls) == 0


@pytest.mark.asyncio
async def test_second_spec_reconfigures_not_redeploys() -> None:
    host = _FakeHost()
    reconciler = _make_reconciler(host=host)

    await reconciler.handle_spec(_spec("s-1", generation=2))
    await reconciler.handle_spec(_spec("s-1", generation=3))

    assert len(host.deploy_calls) == 1
    assert len(host.reconfigure_calls) == 1


@pytest.mark.asyncio
async def test_stopped_lifecycle_triggers_stop() -> None:
    host = _FakeHost()
    reconciler = _make_reconciler(host=host)

    # First reach Running.
    await reconciler.handle_spec(_spec("s-1", generation=2))
    # Then stop.
    await reconciler.handle_spec(_spec("s-1", generation=3, lifecycle="stopped"))

    assert host.stop_calls == ["s-1"]


@pytest.mark.asyncio
async def test_stopped_deployment_reactivation_redeploys() -> None:
    host = _FakeHost()
    vault = _FakeVault()
    reconciler = _make_reconciler(host=host, vault=vault)

    await reconciler.handle_spec(_spec("s-1", generation=1))
    await reconciler.handle_spec(_spec("s-1", generation=2, lifecycle="stopped"))
    await reconciler.handle_spec(_spec("s-1", generation=3))

    assert len(host.deploy_calls) == 2
    assert host.stop_calls == ["s-1"]
    assert host.reconfigure_calls == []
    assert vault.decrypt_calls == ["cred-s-1", "cred-s-1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle", ["stopped", "archived"])
async def test_terminal_lifecycle_reports_stopped_phase(lifecycle: str) -> None:
    host = _FakeHost()
    nats = _FakeNats()
    reconciler = _make_reconciler(host=host, nats=nats)

    await reconciler.handle_spec(_spec("s-1", generation=1, lifecycle=lifecycle))

    assert host.stop_calls == ["s-1"]
    assert nats.status_calls[0][1]["observed_generation"] == 1
    assert nats.status_calls[0][1]["phase"] == "stopped"
    assert nats.status_calls[0][1]["health"] == "healthy"


@pytest.mark.asyncio
async def test_drift_strikes_accumulate_on_failure() -> None:
    host = _FakeHost(deploy_raises=True)
    nats = _FakeNats()
    reconciler = _make_reconciler(host=host, nats=nats)

    # 3 generations each failing → drift_strikes hits threshold.
    for gen in (2, 3, 4):
        await reconciler.handle_spec(_spec("s-1", generation=gen))

    # status should report degraded/unhealthy for each failure
    degraded_reports = [c for c in nats.status_calls if c[1]["phase"] == "degraded"]
    assert len(degraded_reports) == 3


@pytest.mark.asyncio
async def test_publish_status_failure_does_not_abort_loop() -> None:
    """Disconnect safety: when NATS publish fails, reconciler state keeps
    advancing and local host calls continue (lesson #21 + CLAUDE.md
    'disconnect != stop')."""
    host = _FakeHost()
    nats = _FakeNats(publish_raises=True)
    reconciler = _make_reconciler(host=host, nats=nats)

    # publish raises, but handle_spec must not propagate the error
    await reconciler.handle_spec(_spec("s-1", generation=2))
    await reconciler.handle_spec(_spec("s-1", generation=3))

    # host calls still occur
    assert len(host.deploy_calls) == 1
    assert len(host.reconfigure_calls) == 1


@pytest.mark.asyncio
async def test_invalid_generation_logged_not_raised() -> None:
    host = _FakeHost()
    reconciler = _make_reconciler(host=host)

    await reconciler.handle_spec({"spec_id": "s-1", "generation": "not-a-number"})

    # no host call on invalid generation
    assert len(host.deploy_calls) == 0


@pytest.mark.asyncio
async def test_missing_spec_id_logged_not_raised() -> None:
    host = _FakeHost()
    reconciler = _make_reconciler(host=host)

    await reconciler.handle_spec({"generation": 1})

    assert len(host.deploy_calls) == 0
