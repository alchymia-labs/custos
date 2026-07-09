"""Declarative deployment reconcile loop.

云端 NATS-发 DeploymentSpec → runner 本地比对 generation → 调
execution engine 起停策略 → NATS-发 DeploymentStatus 回报。

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
from decimal import Decimal
from typing import Protocol

from custos.core.engine_protocol import ExecutionEngineProtocol
from custos.core.fallback_breaker import FallbackBreaker
from custos.core.g6_gate import check_g6_gate
from custos.core.local_cap import RunnerNotionalCap
from custos.core.log import get_logger
from custos.core.nats_client import ArxNatsClient
from custos.core.zombie_watchdog import ZombieWatchdog

_log = get_logger("custos.deployment_reconciler")


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
    last_spec: dict | None = None


@dataclass
class DeploymentReconciler:
    """声明式 reconcile loop。"""

    nats_client: ArxNatsClient
    tenant_id: str
    runner_id: str
    execution_engine: ExecutionEngineProtocol
    credential_vault: CredentialVaultProtocol
    drift_threshold: int = 3
    poll_interval_secs: float = 0.5
    # Optional local guards injected at the composition root (cli/main.py). When
    # present the reconcile loop enforces them on the disconnect-resilient path;
    # when None the loop behaves as a pure spec follower (unit-test default).
    # local_cap is the pre-trade soft limit (its per-order enforcement lives at
    # the trade path); fallback_breaker + zombie_watchdog run on the loop tick.
    local_cap: RunnerNotionalCap | None = None
    fallback_breaker: FallbackBreaker | None = None
    zombie_watchdog: ZombieWatchdog | None = None
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
            sub = await self.nats_client.subscribe_deployment_spec(strategy_id=strategy_id)
        except Exception as exc:  # noqa: BLE001
            _log.error(
                "deployment_reconciler_subscribe_failed",
                strategy_id=strategy_id,
                error=str(exc),
            )
            return

        while not stop.is_set():
            # Autonomous local guards: run every poll regardless of inbound specs
            # so a stuck / runaway engine is handled even while the cloud is
            # silent (red line 0.3).
            await self._watchdog_tick()
            await self._breaker_tick()
            try:
                msg = await asyncio.wait_for(
                    sub.next_msg(timeout=self.poll_interval_secs),
                    timeout=self.poll_interval_secs * 2,
                )
            except TimeoutError:
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
        # Keep the latest spec so the watchdog can read lifecycle_state (paused
        # exemption) and report status without re-fetching.
        state.last_spec = spec

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
            await self.execution_engine.stop(spec_id)
            return ""
        # 新部署: 解密 credential → 过完整 G6 gate (含 scope 兜底层) → deploy。
        if state.container_id is None:
            cred = self.credential_vault.decrypt(self._credential_ref(spec, spec_id))
            check_g6_gate(self.execution_engine, spec, cred)
            return await self.execution_engine.deploy(spec, cred)
        # 已有部署: reconfigure。gate 复验 host/venue/code_hash; 层 4 scope 已在
        # deploy 时验过, 此处不重新解密 credential。
        check_g6_gate(self.execution_engine, spec, credential=None)
        await self.execution_engine.reconfigure(spec)
        return state.container_id or ""

    async def _watchdog_tick(self) -> None:
        """Probe each deployed spec's engine connectivity and degrade any that
        the zombie watchdog flags. No-op when no watchdog is injected."""
        if self.zombie_watchdog is None:
            return
        for spec_id, state in list(self._state.items()):
            if not state.container_id:
                # Not actively deployed (never started / stopped) — nothing to watch.
                continue
            try:
                connectivity = await self.execution_engine.check_engine_connected(spec_id)
            except Exception as exc:  # noqa: BLE001 — a probe failure must not kill the loop
                _log.warning(
                    "zombie_watchdog_probe_failed",
                    spec_id=spec_id,
                    error=str(exc),
                )
                continue
            paused = bool(state.last_spec and state.last_spec.get("lifecycle_state") == "paused")
            verdict = self.zombie_watchdog.observe(spec_id, connectivity, paused=paused)
            if not verdict.is_zombie:
                continue
            _log.warning(
                "engine_zombie_detected",
                spec_id=spec_id,
                disconnected_secs=verdict.disconnected_secs,
            )
            await self._report_status(
                spec_id=spec_id,
                spec=state.last_spec or {},
                state=state,
                phase="degraded",
                health="unhealthy",
                reason="engine_disconnected_zombie",
            )

    async def _breaker_tick(self) -> None:
        """Evaluate the runner fallback breaker against total open notional and,
        on a trip, flatten every deployed spec. Runs on every poll so a runaway
        runner is contained even while the cloud is unreachable. No-op when no
        breaker is injected.

        The drawdown breach also needs an equity feed; until the equity snapshot
        lands this tick enforces the notional ceiling only (the breaker still
        evaluates drawdown when equity is supplied elsewhere)."""
        if self.fallback_breaker is None:
            return
        active = [spec_id for spec_id, state in self._state.items() if state.container_id]
        if not active:
            return
        total_notional = Decimal("0")
        for spec_id in active:
            try:
                total_notional += await self.execution_engine.get_open_notional(spec_id)
            except Exception as exc:  # noqa: BLE001 — a probe failure must not kill the loop
                _log.warning("breaker_notional_probe_failed", spec_id=spec_id, error=str(exc))
        verdict = self.fallback_breaker.evaluate(open_notional=total_notional)
        if not verdict.tripped:
            return
        _log.warning(
            "fallback_breaker_flatten",
            reason=verdict.reason,
            open_notional=str(total_notional),
        )
        for spec_id in active:
            try:
                await self.execution_engine.flatten_positions(
                    spec_id, verdict.reason or "fallback_breaker"
                )
            except Exception as exc:  # noqa: BLE001 — one flatten failure must not skip the rest
                _log.error("flatten_positions_failed", spec_id=spec_id, error=str(exc))

    @staticmethod
    def _credential_ref(spec: dict, spec_id: str) -> str:
        provenance = spec.get("provenance_ref")
        if isinstance(provenance, dict) and provenance.get("credential_id"):
            return provenance["credential_id"]
        return spec_id  # fallback: use spec_id as opaque cred ref

    async def _report_status(
        self,
        *,
        spec_id: str,
        spec: dict,
        state: _ReconcileState,
        phase: str,
        health: str,
        reason: str | None = None,
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
        if reason is not None:
            payload["health_reason"] = reason
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
