"""Instance-keyed reconciliation of Crucible-signed desired state."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol
from uuid import uuid4

from pydantic import ValidationError

from custos.contracts import CrucibleDomainEventVerifier, DeploymentMessage, DeploymentSpec
from custos.core.engine_protocol import ExecutionEngineProtocol
from custos.core.fallback_breaker import FallbackBreaker, FallbackBreakerConfig
from custos.core.g6_gate import check_g6_gate
from custos.core.local_cap import LocalCapConfig, RunnerNotionalCap
from custos.core.log import get_logger
from custos.core.nats_client import CrucibleNatsClient
from custos.core.runner_deployment_lifecycle_fact import (
    RunnerDeploymentLifecycleFact,
    RunnerDeploymentLifecycleFactEmitter,
)
from custos.core.runner_fact import RunnerFactAuthority, RunnerFactError
from custos.core.runtime_log_fact import RunnerRuntimeLogEmitter, RuntimeLogFactError
from custos.core.zombie_watchdog import ZombieWatchdog

_log = get_logger("custos.deployment_reconciler")
_TERMINAL_STATES = frozenset({"stopped", "archived"})


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
    """Engine apply and durable fact reporting advance independently."""

    applied_generation: int = 0
    reported_generation: int = 0
    container_id: str | None = None
    drift_strikes: int = 0
    last_spec: dict | None = None
    strategy_id: str | None = None
    fact_authority: RunnerFactAuthority | None = None
    runtime_log_authority: RunnerFactAuthority | None = None
    pending_lifecycle_fact: RunnerDeploymentLifecycleFact | None = None


@dataclass
class DeploymentReconciler:
    nats_client: CrucibleNatsClient
    tenant_id: str
    runner_id: str
    execution_engine: ExecutionEngineProtocol
    credential_vault: CredentialVaultProtocol
    runtime_log_emitter: RunnerRuntimeLogEmitter
    lifecycle_fact_emitter: RunnerDeploymentLifecycleFactEmitter
    deployment_verifier: CrucibleDomainEventVerifier
    drift_threshold: int = 3
    poll_interval_secs: float = 0.5
    local_cap: RunnerNotionalCap | None = None
    zombie_watchdog: ZombieWatchdog | None = None
    readiness: ReadinessProtocol | None = None
    subscribe_backoff_initial_secs: float = 0.25
    subscribe_backoff_max_secs: float = 5.0
    _state: dict[str, _ReconcileState] = field(default_factory=dict)
    _fallback_breakers: dict[str, FallbackBreaker] = field(default_factory=dict)

    async def reconcile_loop(self, stop: asyncio.Event) -> None:
        """Verify, apply, durably report, then ACK; local apply failures NAK."""
        _log.info(
            "deployment_reconciler_started",
            tenant_id=self.tenant_id,
            runner_id=self.runner_id,
        )
        if self.readiness is not None:
            self.readiness.clear()
        subscription = None
        backoff = self.subscribe_backoff_initial_secs
        try:
            while not stop.is_set():
                await self._tick_local_guards()
                if subscription is None:
                    try:
                        subscription = await self.nats_client.subscribe_deployment_spec()
                    except Exception as exc:  # noqa: BLE001
                        _log.error(
                            "deployment_reconciler_subscribe_failed",
                            error=str(exc),
                            retry_in_secs=backoff,
                        )
                        await self._wait_for_retry(stop, backoff)
                        backoff = min(backoff * 2, self.subscribe_backoff_max_secs)
                        continue
                    backoff = self.subscribe_backoff_initial_secs
                    if self.readiness is not None:
                        self.readiness.mark_ready(
                            strategy_id=None,
                            nats_connected=True,
                            deployment_subscription=True,
                        )
                try:
                    message = await asyncio.wait_for(
                        subscription.next_msg(timeout=self.poll_interval_secs),
                        timeout=self.poll_interval_secs * 2,
                    )
                except TimeoutError:
                    continue
                except Exception as exc:  # noqa: BLE001
                    _log.warning("deployment_reconciler_subscription_lost", error=str(exc))
                    if self.readiness is not None:
                        self.readiness.clear()
                    subscription = None
                    await self._wait_for_retry(stop, backoff)
                    backoff = min(backoff * 2, self.subscribe_backoff_max_secs)
                    continue
                try:
                    command = DeploymentMessage.parse(
                        message.data,
                        subject=str(message.subject),
                        expected_tenant_id=self.tenant_id,
                        expected_runner_id=self.runner_id,
                        verifier=self.deployment_verifier,
                    )
                except (ValidationError, ValueError, AttributeError) as exc:
                    _log.error("deployment_spec_decode_failed", error=str(exc))
                    terminate = getattr(message, "term", None)
                    if terminate is not None:
                        await terminate()
                    continue
                applied = await self.handle_spec(
                    command.spec.model_dump(mode="json"),
                    strategy_id=str(command.spec.strategy_id),
                )
                disposition = getattr(message, "ack" if applied else "nak", None)
                if disposition is not None:
                    await disposition()
        finally:
            if self.readiness is not None:
                self.readiness.clear()
            _log.info("deployment_reconciler_stopped")

    async def _wait_for_retry(self, stop: asyncio.Event, delay: float) -> None:
        deadline = asyncio.get_running_loop().time() + delay
        while not stop.is_set():
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=min(max(self.poll_interval_secs, 0.001), remaining)
                )
            except TimeoutError:
                await self._tick_local_guards()

    async def handle_spec(self, spec: dict, *, strategy_id: str | None = None) -> bool:
        """Apply each generation once and retry only its durable fact on redelivery."""
        try:
            validated = DeploymentSpec.model_validate(spec)
        except ValidationError as exc:
            _log.error("deployment_spec_validation_failed", error_count=exc.error_count())
            return False
        runtime_spec = validated.model_dump(mode="json")
        instance_id = str(validated.deployment_instance_id)
        generation = validated.generation
        state = self._state.setdefault(instance_id, _ReconcileState())
        effective_strategy_id = strategy_id or str(validated.strategy_id)
        if state.strategy_id is not None and state.strategy_id != effective_strategy_id:
            _log.error("deployment_spec_strategy_identity_changed", deployment_instance_id=instance_id)
            return False
        state.strategy_id = effective_strategy_id
        try:
            authority = self.lifecycle_fact_emitter.authority_for_spec(
                runtime_spec,
                strategy_id=effective_strategy_id,
            )
            runtime_log_authority = self.runtime_log_emitter.authority_for_spec(
                runtime_spec,
                strategy_id=effective_strategy_id,
            )
        except (RuntimeLogFactError, RunnerFactError, ValueError) as exc:
            _log.error(
                "deployment_fact_binding_rejected",
                deployment_instance_id=instance_id,
                error_type=type(exc).__name__,
            )
            return False
        if state.fact_authority is not None and state.fact_authority.stream_key != authority.stream_key:
            _log.error("deployment_fact_binding_changed", deployment_instance_id=instance_id)
            return False
        if runtime_log_authority.stream_key != authority.stream_key:
            _log.error("deployment_fact_authorities_disagree", deployment_instance_id=instance_id)
            return False
        state.fact_authority = authority
        state.runtime_log_authority = runtime_log_authority

        if state.reported_generation < state.applied_generation:
            if state.last_spec is None or not await self._report_applied_generation(
                state,
                state.last_spec,
            ):
                return False

        if generation < state.applied_generation:
            _log.warning(
                "deployment_spec_stale",
                deployment_instance_id=instance_id,
                spec_generation=generation,
                applied_generation=state.applied_generation,
            )
            return True
        if generation == state.applied_generation:
            if state.reported_generation < generation:
                return await self._report_applied_generation(state, runtime_spec)
            return True

        state.last_spec = runtime_spec
        try:
            state.container_id = await self._apply_spec(instance_id, runtime_spec, state)
        except Exception as exc:  # noqa: BLE001
            state.drift_strikes += 1
            _log.error(
                "deployment_reconcile_failed",
                deployment_instance_id=instance_id,
                error=str(exc),
                drift_strikes=state.drift_strikes,
            )
            await self._emit_runtime_log(
                state,
                level="ERROR",
                message="Deployment apply failed",
                fields={"generation": generation, "error_type": type(exc).__name__},
            )
            return False
        self._refresh_instance_guards(instance_id, runtime_spec)
        state.applied_generation = generation
        state.drift_strikes = 0
        if validated.lifecycle_state.value in _TERMINAL_STATES:
            self._fallback_breakers.pop(instance_id, None)
            if self.zombie_watchdog is not None:
                self.zombie_watchdog.forget(instance_id)
        return await self._report_applied_generation(state, runtime_spec)

    async def _apply_spec(
        self,
        instance_id: str,
        spec: dict,
        state: _ReconcileState,
    ) -> str:
        lifecycle = str(spec["lifecycle_state"])
        if lifecycle in _TERMINAL_STATES:
            await self.execution_engine.stop(instance_id)
            return ""
        if not state.container_id:
            credential = self.credential_vault.decrypt(self._credential_ref(spec, instance_id))
            check_g6_gate(self.execution_engine, spec, credential)
            return await self.execution_engine.deploy(spec, credential)
        check_g6_gate(self.execution_engine, spec, credential=None)
        await self.execution_engine.reconfigure(spec)
        return state.container_id

    def _refresh_instance_guards(self, instance_id: str, spec: dict) -> None:
        live = spec.get("trading_mode") == "live"
        if self.local_cap is not None:
            self.local_cap.apply_config(LocalCapConfig.from_spec(spec, live=live))
        config = FallbackBreakerConfig.from_spec(spec)
        breaker = self._fallback_breakers.get(instance_id)
        if breaker is None:
            self._fallback_breakers[instance_id] = FallbackBreaker(config)
        else:
            breaker.apply_config(config)

    async def _report_applied_generation(self, state: _ReconcileState, spec: dict) -> bool:
        authority = state.fact_authority
        if authority is None:
            return False
        generation = int(spec["generation"])
        if state.pending_lifecycle_fact is None:
            state.pending_lifecycle_fact = RunnerDeploymentLifecycleFact.observed(
                authority,
                generation=generation,
                lifecycle_state=str(spec["lifecycle_state"]),
            )
        try:
            await self.lifecycle_fact_emitter.emit_fact(
                authority,
                state.pending_lifecycle_fact,
            )
        except Exception as exc:  # noqa: BLE001
            _log.error(
                "deployment_lifecycle_fact_enqueue_failed",
                deployment_instance_id=str(authority.deployment_instance_id),
                generation=generation,
                error_type=type(exc).__name__,
            )
            return False
        state.reported_generation = generation
        state.pending_lifecycle_fact = None
        await self._emit_runtime_log(
            state,
            level="INFO",
            message="Deployment lifecycle applied",
            fields={
                "generation": generation,
                "lifecycle_state": spec["lifecycle_state"],
                "applied_generation": state.applied_generation,
                "reported_generation": state.reported_generation,
            },
        )
        return True

    async def _emit_runtime_log(
        self,
        state: _ReconcileState,
        *,
        level: str,
        message: str,
        fields: dict,
    ) -> None:
        if state.runtime_log_authority is None:
            return
        try:
            await self.runtime_log_emitter.emit(
                state.runtime_log_authority,
                level=level,
                component="deployment_reconciler",
                message=message,
                structured_fields=fields,
                correlation_id=uuid4(),
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "runner_runtime_log_fact_skipped",
                deployment_instance_id=str(state.runtime_log_authority.deployment_instance_id),
                error_type=type(exc).__name__,
            )

    def active_deployment_instance_ids(self) -> list[str]:
        return [key for key, state in self._state.items() if state.container_id]

    async def _tick_local_guards(self) -> None:
        await self._watchdog_tick()
        await self._breaker_tick()

    async def _watchdog_tick(self) -> None:
        if self.zombie_watchdog is None:
            return
        for instance_id, state in tuple(self._state.items()):
            if not state.container_id:
                continue
            try:
                connectivity = await self.execution_engine.check_engine_connected(instance_id)
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "zombie_watchdog_probe_failed",
                    deployment_instance_id=instance_id,
                    error_type=type(exc).__name__,
                )
                continue
            paused = bool(state.last_spec and state.last_spec.get("lifecycle_state") == "paused")
            verdict = self.zombie_watchdog.observe(instance_id, connectivity, paused=paused)
            if verdict.is_zombie:
                await self._emit_runtime_log(
                    state,
                    level="ERROR",
                    message="Execution engine connectivity degraded",
                    fields={"disconnected_secs": verdict.disconnected_secs},
                )

    async def _breaker_tick(self) -> None:
        for instance_id, breaker in tuple(self._fallback_breakers.items()):
            state = self._state.get(instance_id)
            if state is None or not state.container_id:
                continue
            try:
                notional = await self.execution_engine.get_open_notional(instance_id)
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "breaker_notional_probe_failed",
                    deployment_instance_id=instance_id,
                    error_type=type(exc).__name__,
                )
                continue
            equity: Decimal | None
            try:
                equity = (await self.execution_engine.get_engine_status(instance_id)).current_equity
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "breaker_equity_probe_failed",
                    deployment_instance_id=instance_id,
                    error_type=type(exc).__name__,
                )
                equity = None
            was_frozen = breaker.frozen
            verdict = breaker.evaluate(open_notional=notional, current_equity=equity)
            if not verdict.tripped or was_frozen:
                continue
            try:
                await self.execution_engine.flatten_positions(
                    instance_id,
                    verdict.reason or "fallback_breaker",
                )
            except Exception as exc:  # noqa: BLE001
                _log.error(
                    "flatten_positions_failed",
                    deployment_instance_id=instance_id,
                    error_type=type(exc).__name__,
                )
            await self._emit_runtime_log(
                state,
                level="ERROR",
                message="Instance fallback breaker tripped",
                fields={"reason": verdict.reason, "open_notional": str(notional)},
            )

    @staticmethod
    def _credential_ref(spec: dict, instance_id: str) -> str:
        provenance = spec.get("provenance_ref")
        if isinstance(provenance, dict) and provenance.get("credential_id"):
            return str(provenance["credential_id"])
        return instance_id
