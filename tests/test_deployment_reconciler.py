from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

import pytest

from custos.core.deployment_reconciler import DeploymentReconciler
from custos.core.engine_protocol import ConnectivityState, EngineStatus
from custos.core.runner_fact import RunnerFactAuthority

SHA = "a" * 64
RUNNER = UUID("10000000-0000-4000-8000-000000000001")
STRATEGY = UUID("40000000-0000-4000-8000-000000000004")


def spec(instance: str, *, generation: int = 1, max_notional: str = "10") -> dict:
    return {
        "spec_id": "30000000-0000-4000-8000-000000000003",
        "deployment_instance_id": instance,
        "deployment_spec_digest": SHA,
        "strategy_id": str(STRATEGY),
        "generation": generation,
        "trading_mode": "sandbox",
        "lifecycle_state": "running",
        "strategy_path": "/tmp/strategy",
        "provenance_ref": {"credential_id": "sandbox-credential"},
        "connector": "binance",
        "pairs": ["BTC-USDT"],
        "leverage": 1,
        "strategy_config": {},
        "code_hash": SHA,
        "sandbox": {"starting_balances": ["10000 USDT"]},
        "risk_config": {"fallback_breaker": {"max_notional": max_notional}},
    }


@dataclass
class FakeEngine:
    deploy_calls: list[str] = field(default_factory=list)
    flatten_calls: list[str] = field(default_factory=list)
    notionals: dict[str, Decimal] = field(default_factory=dict)

    async def deploy(self, value: dict, credential: dict) -> str:
        instance = value["deployment_instance_id"]
        self.deploy_calls.append(instance)
        return instance

    async def reconfigure(self, value: dict) -> None:
        return None

    async def stop(self, deployment_instance_id: str) -> None:
        return None

    def supports_live(self) -> bool:
        return True

    def supports_venue(self, venue: str) -> bool:
        return True
    async def get_open_notional(self, deployment_instance_id: str) -> Decimal:
        return self.notionals.get(deployment_instance_id, Decimal("0"))
    async def check_engine_connected(self, deployment_instance_id: str) -> ConnectivityState:
        return ConnectivityState(data_connected=True, exec_connected=True)
    async def flatten_positions(self, deployment_instance_id: str, reason: str) -> None:
        self.flatten_calls.append(deployment_instance_id)
    async def get_engine_status(self, deployment_instance_id: str) -> EngineStatus:
        return EngineStatus(
            phase="running", position_count=0, order_count=0,
            open_notional=self.notionals.get(deployment_instance_id, Decimal("0")),
            peak_equity=Decimal("100"), current_equity=Decimal("100"),
            drawdown_pct=Decimal("0"),
        )


class FakeRuntimeLogEmitter:
    def authority_for_spec(self, value: dict, *, strategy_id: str) -> RunnerFactAuthority:
        return RunnerFactAuthority(
            tenant_id="acme", trading_mode=value["trading_mode"], runner_id=RUNNER,
            deployment_instance_id=UUID(value["deployment_instance_id"]),
            deployment_spec_id=UUID(value["spec_id"]), deployment_spec_digest=SHA,
            strategy_id=UUID(strategy_id),
            capability_version_id=UUID("50000000-0000-4000-8000-000000000005"),
            capability_version=1, capability_manifest_digest=SHA,
        )
    async def emit(self, *args, **kwargs):
        return None


@dataclass
class FakeLifecycleEmitter:
    fail_once: bool = False
    calls: list[tuple[str, int]] = field(default_factory=list)

    def authority_for_spec(self, value: dict, *, strategy_id: str) -> RunnerFactAuthority:
        return FakeRuntimeLogEmitter().authority_for_spec(value, strategy_id=strategy_id)

    async def emit_fact(self, authority, fact):
        self.calls.append((str(authority.deployment_instance_id), fact.generation))
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("outbox unavailable")


class FakeVault:
    def decrypt(self, credential_id: str) -> dict:
        return {"permission_scope": "sandbox"}


def reconciler(engine: FakeEngine, lifecycle: FakeLifecycleEmitter) -> DeploymentReconciler:
    return DeploymentReconciler(
        nats_client=object(), tenant_id="acme", runner_id=str(RUNNER),
        execution_engine=engine, credential_vault=FakeVault(),
        runtime_log_emitter=FakeRuntimeLogEmitter(),
        lifecycle_fact_emitter=lifecycle, deployment_verifier=object(),
    )


@pytest.mark.asyncio
async def test_fact_failure_naks_and_redelivery_does_not_repeat_engine_action(monkeypatch) -> None:
    monkeypatch.setattr("custos.core.deployment_reconciler.check_g6_gate", lambda *args: None)
    engine = FakeEngine()
    lifecycle = FakeLifecycleEmitter(fail_once=True)
    value = spec("20000000-0000-4000-8000-000000000002")
    subject = reconciler(engine, lifecycle)
    assert await subject.handle_spec(value) is False
    assert subject._state[value["deployment_instance_id"]].applied_generation == 1
    assert subject._state[value["deployment_instance_id"]].reported_generation == 0
    assert await subject.handle_spec(value) is True
    assert engine.deploy_calls == [value["deployment_instance_id"]]
    assert subject._state[value["deployment_instance_id"]].reported_generation == 1


@pytest.mark.asyncio
async def test_breakers_are_isolated_per_deployment_instance(monkeypatch) -> None:
    monkeypatch.setattr("custos.core.deployment_reconciler.check_g6_gate", lambda *args: None)
    first = "20000000-0000-4000-8000-000000000002"
    second = "21000000-0000-4000-8000-000000000002"
    engine = FakeEngine(notionals={first: Decimal("11"), second: Decimal("5")})
    subject = reconciler(engine, FakeLifecycleEmitter())
    assert await subject.handle_spec(spec(first, max_notional="10"))
    assert await subject.handle_spec(spec(second, max_notional="20"))
    await subject._breaker_tick()
    assert set(subject._fallback_breakers) == {first, second}
    assert engine.flatten_calls == [first]
