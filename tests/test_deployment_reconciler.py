"""DeploymentReconciler — generation 幂等 + drift + 失联安全。

测试覆盖 plan-index §6 + Plan 06 reconcile 契约:
- generation diff → 触发 reconcile (deploy 调用)
- 同 generation → no-op (幂等)
- 旧 generation → stale 拒绝, 不重复调 host
- drift_strikes 计数 (NautilusHost 持续失败 → DriftDetected)
- 状态报告: publish_deployment_status 包含正确 observed_generation
- 失联安全 (CLAUDE.md 红线): NATS 断连 publish 失败时 reconcile loop
  本地状态依然推进, host 调用不停。
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


def _spec(spec_id: str, generation: int, lifecycle: str = "paper") -> dict:
    return {
        "spec_id": spec_id,
        "generation": generation,
        "lifecycle_state": lifecycle,
        "provenance_ref": {"credential_id": f"cred-{spec_id}"},
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
    """失联安全: NATS publish 失败时 reconciler 状态依然推进,
    本地 host 调用持续进行 (lesson #21 + CLAUDE.md '失联≠停止')。"""
    host = _FakeHost()
    nats = _FakeNats(publish_raises=True)
    reconciler = _make_reconciler(host=host, nats=nats)

    # publish 会 raise 但 handle_spec 不传播
    await reconciler.handle_spec(_spec("s-1", generation=2))
    await reconciler.handle_spec(_spec("s-1", generation=3))

    # host 调用照常发生
    assert len(host.deploy_calls) == 1
    assert len(host.reconfigure_calls) == 1


@pytest.mark.asyncio
async def test_invalid_generation_logged_not_raised() -> None:
    host = _FakeHost()
    reconciler = _make_reconciler(host=host)

    await reconciler.handle_spec({"spec_id": "s-1", "generation": "not-a-number"})

    # 不调 host
    assert len(host.deploy_calls) == 0


@pytest.mark.asyncio
async def test_missing_spec_id_logged_not_raised() -> None:
    host = _FakeHost()
    reconciler = _make_reconciler(host=host)

    await reconciler.handle_spec({"generation": 1})

    assert len(host.deploy_calls) == 0
