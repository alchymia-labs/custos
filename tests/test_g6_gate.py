"""G6 gate — live mode 下 NoopHost 部署拦截 (failure-mode 覆盖契约)。

三场景 (失败模式覆盖 + 每层独立可测):
- live + NoopHost → 拒 (RuntimeError "G6 gate") + structlog error
- paper + NoopHost → 允许 (deploy 正常, 不回归)
- live + 非 NoopHost (协议兼容 NtHost stub) → 允许 (relaxed double 证明 gate 只挡 NoopHost)

gate 位于 DeploymentReconciler._apply_spec 的 deploy/reconfigure 分支前 (stop 分支
豁免: 停止一个 live+stub 部署是安全的)。测试直接调 _apply_spec —— 这是 gate 所在
的 guard 层; handle_spec 的 broad except 会吞异常, 故在此层断言 raise 才可观测。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
import structlog

from arx_runner.deployment_reconciler import DeploymentReconciler, _ReconcileState
from arx_runner.nautilus_host import NoopHost


@dataclass
class _FakeVault:
    def decrypt(self, credential_id: str) -> dict:
        return {"credential_id": credential_id, "secret": "<fake>"}


@dataclass
class _FakeNats:
    async def publish_deployment_status(self, *, spec_id: str, payload: dict) -> None:
        return None


@dataclass
class _FakeNtHost:
    """Non-NoopHost 协议兼容 stub — 作为 NtTradingNodeHost 占位过 G6 gate。

    relaxed double: 故意不是 NoopHost, 证明 gate 只拦 NoopHost 而非拦所有 live
    (inner guard 是 live guard 而非 dead branch)。
    """

    deploy_calls: list = field(default_factory=list)

    async def deploy(self, spec: dict, credential: dict) -> str:
        self.deploy_calls.append((spec, credential))
        return f"container-{spec['spec_id']}"

    async def reconfigure(self, spec: dict) -> None:
        return None

    async def stop(self, spec_id: str) -> None:
        return None


def _make_reconciler(host) -> DeploymentReconciler:
    return DeploymentReconciler(
        nats_client=_FakeNats(),  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id="runner-7",
        nautilus_host=host,
        credential_vault=_FakeVault(),  # type: ignore[arg-type]
    )


def _spec(spec_id: str, trading_mode: str) -> dict:
    return {
        "spec_id": spec_id,
        "generation": 1,
        "trading_mode": trading_mode,
        "lifecycle_state": "running",
        "provenance_ref": {"credential_id": f"cred-{spec_id}"},
    }


@pytest.mark.parametrize("mode", ["Live", "live", "LIVE"])
@pytest.mark.asyncio
async def test_g6_gate_rejects_live_noophost(mode: str) -> None:
    # "Live" 是 Rust TradingMode enum 默认 serde 序列化 (PascalCase) 的真实 wire 值;
    # 大小写变体一并断言, 防 gate 因大小写失配沦为 dead gate。
    reconciler = _make_reconciler(NoopHost())
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(RuntimeError, match="G6 gate"):
            await reconciler._apply_spec(_spec("s1", mode), _ReconcileState())
    events = [entry.get("event") for entry in logs]
    assert "g6_gate_live_noophost_rejected" in events


@pytest.mark.asyncio
async def test_g6_gate_allows_paper_noophost() -> None:
    reconciler = _make_reconciler(NoopHost())
    container_id = await reconciler._apply_spec(_spec("s2", "paper"), _ReconcileState())
    assert container_id == "container-s2"


@pytest.mark.asyncio
async def test_g6_gate_allows_live_nt_host() -> None:
    host = _FakeNtHost()
    reconciler = _make_reconciler(host)
    # 真实 live wire 值 "Live" + 非 NoopHost → gate 放行 (relaxed double)。
    container_id = await reconciler._apply_spec(_spec("s3", "Live"), _ReconcileState())
    assert container_id == "container-s3"
    assert len(host.deploy_calls) == 1
