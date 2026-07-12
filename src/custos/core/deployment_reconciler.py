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
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from pydantic import ValidationError

from custos.contracts import DeploymentMessage, DeploymentSpec, TradingMode
from custos.core.engine_protocol import ExecutionEngineProtocol
from custos.core.fallback_breaker import FallbackBreaker, FallbackBreakerConfig
from custos.core.g6_gate import check_g6_gate
from custos.core.local_cap import LocalCapConfig, RunnerNotionalCap
from custos.core.log import get_logger
from custos.core.nats_client import ArxNatsClient, build_subject
from custos.core.zombie_watchdog import ZombieWatchdog

_log = get_logger("custos.deployment_reconciler")


class CredentialVaultProtocol(Protocol):
    def decrypt(self, credential_id: str) -> dict: ...


class ReadinessProtocol(Protocol):
    def mark_ready(
        self,
        *,
        strategy_id: str | None,
        nats_connected: bool,
        deployment_subscription: bool,
    ) -> None: ...

    def clear(self) -> None: ...


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
    readiness: ReadinessProtocol | None = None
    subscribe_backoff_initial_secs: float = 0.25
    subscribe_backoff_max_secs: float = 5.0
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
        if self.readiness is not None:
            self.readiness.clear()
        sub = None
        backoff = self.subscribe_backoff_initial_secs
        try:
            while not stop.is_set():
                # Autonomous local guards run whether subscribed, retrying, or idle.
                await self._tick_local_guards()
                if sub is None:
                    try:
                        sub = await self.nats_client.subscribe_deployment_spec(
                            strategy_id=strategy_id
                        )
                    except Exception as exc:  # noqa: BLE001 - retry until stop
                        _log.error(
                            "deployment_reconciler_subscribe_failed",
                            strategy_id=strategy_id,
                            error=str(exc),
                            retry_in_secs=backoff,
                        )
                        await self._wait_for_retry(stop, backoff)
                        backoff = min(backoff * 2, self.subscribe_backoff_max_secs)
                        continue
                    backoff = self.subscribe_backoff_initial_secs
                    _log.info(
                        "deployment_reconciler_subscribed",
                        strategy_id=strategy_id,
                    )
                    if self.readiness is not None:
                        self.readiness.mark_ready(
                            strategy_id=strategy_id,
                            nats_connected=True,
                            deployment_subscription=True,
                        )

                try:
                    msg = await asyncio.wait_for(
                        sub.next_msg(timeout=self.poll_interval_secs),
                        timeout=self.poll_interval_secs * 2,
                    )
                except TimeoutError:
                    continue
                except Exception as exc:  # noqa: BLE001 - clear readiness and resubscribe
                    _log.warning(
                        "deployment_reconciler_subscription_lost",
                        strategy_id=strategy_id,
                        error=str(exc),
                    )
                    if self.readiness is not None:
                        self.readiness.clear()
                    sub = None
                    await self._wait_for_retry(stop, backoff)
                    backoff = min(backoff * 2, self.subscribe_backoff_max_secs)
                    continue

                try:
                    message = DeploymentMessage.parse(
                        msg.data,
                        expected_tenant_id=self.tenant_id,
                    )
                except (ValidationError, ValueError, AttributeError) as exc:
                    _log.error(
                        "deployment_spec_decode_failed",
                        error=str(exc),
                    )
                    continue
                expected_subject = build_subject(self.tenant_id, "deployment_spec", strategy_id)
                if message.subject != expected_subject:
                    _log.error(
                        "deployment_message_strategy_mismatch",
                        expected_subject=expected_subject,
                        message_subject=message.subject,
                    )
                    continue
                await self.handle_spec(message.spec.model_dump(mode="json"))
        finally:
            if self.readiness is not None:
                self.readiness.clear()
            _log.info(
                "deployment_reconciler_stopped",
                session_id=self.session_id,
            )

    async def _tick_local_guards(self) -> None:
        await self._watchdog_tick()
        await self._breaker_tick()

    async def _wait_for_retry(self, stop: asyncio.Event, delay: float) -> None:
        deadline = asyncio.get_running_loop().time() + delay
        while not stop.is_set():
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return
            interval = min(max(self.poll_interval_secs, 0.001), remaining)
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except TimeoutError:
                await self._tick_local_guards()

    async def handle_spec(self, spec: dict) -> None:
        """Process one DeploymentSpec snapshot. Generation 幂等 + drift 检测。"""
        try:
            validated = DeploymentSpec.model_validate(spec)
        except ValidationError as exc:
            _log.error(
                "deployment_spec_validation_failed",
                error_count=exc.error_count(),
            )
            return
        spec = validated.model_dump(mode="json")
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

        # Live-refresh the runner-wide risk guards from this spec's
        # ``risk_config`` before evaluating generation drift. docs/domain.md
        # L104 promises "daemon reads risk_config from the spec and changes
        # take effect next loop" — running the refresh outside the generation
        # gate lets a spec that is otherwise a no-op still push new limits.
        self._refresh_risk_config(spec)

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
            phase = (
                "stopped" if spec.get("lifecycle_state") in ("stopped", "archived") else "running"
            )
            await self._report_status(
                spec_id=spec_id,
                spec=spec,
                state=state,
                phase=phase,
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
        # A successful stop stores an empty container id. Any later active
        # generation must create a fresh engine instance, not reconfigure the
        # instance that stop() already removed.
        if not state.container_id:
            cred = self.credential_vault.decrypt(self._credential_ref(spec, spec_id))
            check_g6_gate(self.execution_engine, spec, cred)
            return await self.execution_engine.deploy(spec, cred)
        # 已有部署: reconfigure。gate 复验 host/venue/code_hash; 层 4 scope 已在
        # deploy 时验过, 此处不重新解密 credential。
        check_g6_gate(self.execution_engine, spec, credential=None)
        await self.execution_engine.reconfigure(spec)
        return state.container_id or ""

    def _refresh_risk_config(self, spec: dict) -> None:
        """Re-read local guard configs from ``spec.risk_config``.

        Called on every accepted spec so cloud-side operator edits to
        ``max_notional_per_runner`` / ``fallback_breaker.max_notional`` /
        ``fallback_breaker.max_drawdown_pct`` take effect on the next loop.
        Emits a single structured ``risk_config_refreshed`` event when
        anything actually changed — a no-op refresh stays silent so the log
        signal remains meaningful (audit-not-silent + no-log-spam)."""

        live = spec.get("trading_mode") == TradingMode.LIVE.value
        changed = False

        if self.local_cap is not None:
            if self.local_cap.apply_config(LocalCapConfig.from_spec(spec, live=live)):
                changed = True

        if self.fallback_breaker is not None:
            if self.fallback_breaker.apply_config(FallbackBreakerConfig.from_spec(spec)):
                changed = True

        if changed:
            _log.info(
                "risk_config_refreshed",
                spec_id=spec.get("spec_id"),
                generation=spec.get("generation"),
                trading_mode=spec.get("trading_mode"),
                lifecycle_state=spec.get("lifecycle_state"),
                cap=str(self.local_cap.config.max_notional_per_runner)
                if self.local_cap is not None
                else None,
                breaker_max_notional=str(self.fallback_breaker._config.max_notional)
                if self.fallback_breaker is not None
                else None,
                breaker_max_drawdown_pct=str(self.fallback_breaker._config.max_drawdown_pct)
                if self.fallback_breaker is not None
                else None,
            )

    def active_spec_ids(self) -> list[str]:
        """Spec ids the reconciler has actively deployed (``container_id`` set).
        The state snapshot publisher iterates this each interval so a runner
        with N concurrent deployments publishes one snapshot per active spec.
        Reading through this method keeps composition-root code out of the
        reconciler's ``_state`` internals."""
        return [spec_id for spec_id, state in self._state.items() if state.container_id]

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
        """Evaluate the runner fallback breaker against total open notional
        and total current equity across every deployed spec; on a trip,
        flatten every deployed spec. Runs on every poll so a runaway runner
        is contained even while the cloud is unreachable. No-op when no
        breaker is injected.

        Equity comes from the engine's Tier-2 ``get_engine_status`` — summing
        ``current_equity`` across active specs gives the runner-wide feed the
        breaker's drawdown check needs. A ``get_engine_status`` probe failure
        degrades to notional-only evaluation for that tick (better than
        skipping the whole tick and letting a runaway notional slip).
        """

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
        total_equity: Decimal | None = Decimal("0")
        for spec_id in active:
            try:
                status = await self.execution_engine.get_engine_status(spec_id)
                total_equity = (total_equity or Decimal("0")) + status.current_equity
            except Exception as exc:  # noqa: BLE001 — equity probe failure degrades to notional-only
                _log.warning("breaker_equity_probe_failed", spec_id=spec_id, error=str(exc))
                total_equity = None
                break
        was_frozen = self.fallback_breaker.frozen
        verdict = self.fallback_breaker.evaluate(
            open_notional=total_notional,
            current_equity=total_equity,
        )
        if not verdict.tripped:
            return
        if was_frozen:
            # First-trip tick already dispatched flatten; re-issuing every tick
            # after freeze would spam the exchange until an operator resets.
            return
        _log.warning(
            "fallback_breaker_flatten",
            reason=verdict.reason,
            open_notional=str(total_notional),
            current_equity=str(total_equity) if total_equity is not None else "unavailable",
            drawdown_pct=str(verdict.drawdown_pct),
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
