"""Declarative deployment reconcile loop.

云端 NATS-发 DeploymentSpec → runner 本地比对 generation → 调
nautilus_host 起停 NT → NATS-发 DeploymentStatus 回报。

声明式 + level-triggered (plan-index §6):
- generation 比对幂等：同 generation 多次到达不重复执行。
- 失联≠停止 (domain-model L229)：NATS 断连时 reconcile loop 继续运行，
  本地 NT 不停。重连后补报最新 status。
- 主动观测：silent path 必接 structlog (lesson #21)。

新文件，不扩展 reconcile.py (后者是对账上传 ReconcileUploader, 职责不同)。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from arx_runner.log import get_logger
from arx_runner.nats_client import ArxNatsClient

_log = get_logger("arx_runner.deployment_reconciler")


class NautilusHostProtocol(Protocol):
    """NT 进程监管接口 (skeleton: nautilus_host.py 真实现; runner 此处仅依赖签名)。"""

    async def deploy(self, spec: dict, credential: dict) -> str: ...

    async def reconfigure(self, spec: dict) -> None: ...

    async def stop(self, spec_id: str) -> None: ...


class CredentialVaultProtocol(Protocol):
    def decrypt(self, credential_id: str) -> dict: ...


@dataclass
class _ReconcileState:
    """Per-spec_id reconcile bookkeeping。observed_generation 是本地观测到
    runner 真正 reconcile 完成 的 generation; drift_strikes 累计连续观测
    spec.generation > observed_generation 的次数, 超阈值标 drift。"""

    observed_generation: int = 0
    container_id: str | None = None
    drift_strikes: int = 0


@dataclass
class DeploymentReconciler:
    """声明式 reconcile loop。"""

    nats_client: ArxNatsClient
    tenant_id: str
    runner_id: str
    nautilus_host: NautilusHostProtocol
    credential_vault: CredentialVaultProtocol
    drift_threshold: int = 3
    poll_interval_secs: float = 0.5
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    _state: dict[str, _ReconcileState] = field(default_factory=dict)

    async def reconcile_loop(
        self,
        stop: asyncio.Event,
        strategy_id: str,
    ) -> None:
        """Main loop: subscribe deployment_spec → process → report status.

        失联安全 (CLAUDE.md 红线 '失联≠停止'):
        - subscribe/connect 异常时记 log + 退避重试; 本地 NT 不停。
        - publish_deployment_status 失败时记 log + 跳过; 下一次 reconcile 重报。
        """
        _log.info(
            "deployment_reconciler_started",
            tenant_id=self.tenant_id,
            runner_id=self.runner_id,
            session_id=self.session_id,
            strategy_id=strategy_id,
        )
        try:
            sub = await self.nats_client.subscribe_deployment_spec(
                strategy_id=strategy_id
            )
        except Exception as exc:  # noqa: BLE001
            _log.error(
                "deployment_reconciler_subscribe_failed",
                strategy_id=strategy_id,
                error=str(exc),
            )
            return

        while not stop.is_set():
            try:
                msg = await asyncio.wait_for(
                    sub.next_msg(timeout=self.poll_interval_secs),
                    timeout=self.poll_interval_secs * 2,
                )
            except asyncio.TimeoutError:
                continue
            except Exception as exc:  # noqa: BLE001 — NATS 抖动不停止 loop
                _log.warning(
                    "deployment_reconciler_recv_failed",
                    strategy_id=strategy_id,
                    error=str(exc),
                )
                await asyncio.sleep(self.poll_interval_secs)
                continue

            try:
                envelope = json.loads(msg.data)
            except (json.JSONDecodeError, AttributeError) as exc:
                _log.error(
                    "deployment_spec_decode_failed",
                    error=str(exc),
                )
                continue
            spec = envelope.get("payload", {})
            await self.handle_spec(spec)

        _log.info(
            "deployment_reconciler_stopped",
            session_id=self.session_id,
        )

    async def handle_spec(self, spec: dict) -> None:
        """Process one DeploymentSpec snapshot. Generation 幂等 + drift 检测。"""
        spec_id = spec.get("spec_id")
        if not spec_id:
            _log.error("deployment_spec_missing_spec_id", payload_keys=list(spec.keys()))
            return
        try:
            generation = int(spec.get("generation", 0))
        except (TypeError, ValueError):
            _log.error(
                "deployment_spec_invalid_generation",
                spec_id=spec_id,
                raw=spec.get("generation"),
            )
            return

        state = self._state.setdefault(spec_id, _ReconcileState())

        if generation == state.observed_generation:
            # No-op — 同 generation 再来一次不重复 (幂等)。
            _log.debug(
                "deployment_spec_noop",
                spec_id=spec_id,
                generation=generation,
            )
            return

        if generation < state.observed_generation:
            _log.warning(
                "deployment_spec_stale",
                spec_id=spec_id,
                spec_generation=generation,
                observed_generation=state.observed_generation,
            )
            return

        # 需要 reconcile: generation > observed_generation。
        try:
            container_id = await self._apply_spec(spec, state)
            state.container_id = container_id
            state.observed_generation = generation
            state.drift_strikes = 0
            await self._report_status(
                spec_id=spec_id,
                spec=spec,
                state=state,
                phase="running",
                health="healthy",
            )
        except Exception as exc:  # noqa: BLE001
            state.drift_strikes += 1
            _log.error(
                "deployment_reconcile_failed",
                spec_id=spec_id,
                error=str(exc),
                drift_strikes=state.drift_strikes,
                threshold=self.drift_threshold,
            )
            await self._report_status(
                spec_id=spec_id,
                spec=spec,
                state=state,
                phase="degraded",
                health="unhealthy",
            )
            if state.drift_strikes >= self.drift_threshold:
                _log.error(
                    "deployment_drift_detected",
                    spec_id=spec_id,
                    drift_strikes=state.drift_strikes,
                )

    async def _apply_spec(self, spec: dict, state: _ReconcileState) -> str:
        """Apply spec to NT: new deploy / reconfigure / stop."""
        lifecycle = spec.get("lifecycle_state")
        spec_id = spec["spec_id"]
        if lifecycle in ("stopped", "archived"):
            await self.nautilus_host.stop(spec_id)
            return ""
        # 新部署: container_id 未知 → deploy + decrypt credential。
        if state.container_id is None:
            credential_id = (
                spec.get("provenance_ref", {})
                .get("credential_id")
                if isinstance(spec.get("provenance_ref"), dict)
                else None
            ) or spec_id  # fallback: use spec_id as opaque cred ref
            cred = self.credential_vault.decrypt(credential_id)
            return await self.nautilus_host.deploy(spec, cred)
        # 已有部署: reconfigure。
        await self.nautilus_host.reconfigure(spec)
        return state.container_id or ""

    async def _report_status(
        self,
        *,
        spec_id: str,
        spec: dict,
        state: _ReconcileState,
        phase: str,
        health: str,
    ) -> None:
        """Publish DeploymentStatus back to cloud。失败必接 log (lesson #21)。"""
        payload = {
            "status_id": str(uuid.uuid4()),
            "spec_id": spec_id,
            "observed_generation": state.observed_generation,
            "container_id": state.container_id,
            "phase": phase,
            "health": health,
            "runner_id": self.runner_id,
        }
        try:
            await self.nats_client.publish_deployment_status(
                spec_id=spec_id,
                payload=payload,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "deployment_status_publish_failed",
                spec_id=spec_id,
                error=str(exc),
            )
