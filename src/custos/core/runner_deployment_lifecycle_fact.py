"""Typed deployment lifecycle observations emitted through RunnerFactOutbox."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import uuid6

from custos.core.runner_fact import (
    RunnerCapabilityReceipt,
    RunnerFactAuthority,
    RunnerFactEmitter,
)

LIFECYCLE_FACT_KIND = "RunnerDeploymentLifecycleFact.v1"
_LIFECYCLE_STATES = frozenset({"running", "paused", "stopped", "archived"})


def _now_rfc3339_nanos() -> str:
    ns = time.time_ns()
    seconds, remainder = divmod(ns, 1_000_000_000)
    value = datetime.fromtimestamp(seconds, tz=UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S") + f".{remainder:09d}Z"


@dataclass(frozen=True, slots=True)
class RunnerDeploymentLifecycleFact:
    tenant_id: str
    mode: str
    runner_id: UUID
    deployment_instance_id: UUID
    deployment_spec_id: UUID
    deployment_spec_digest: str
    generation: int
    lifecycle_state: str
    observed_at: str
    event_id: UUID

    @classmethod
    def observed(
        cls,
        authority: RunnerFactAuthority,
        *,
        generation: int,
        lifecycle_state: str,
    ) -> RunnerDeploymentLifecycleFact:
        return cls(
            tenant_id=authority.tenant_id,
            mode=authority.trading_mode,
            runner_id=authority.runner_id,
            deployment_instance_id=authority.deployment_instance_id,
            deployment_spec_id=authority.deployment_spec_id,
            deployment_spec_digest=authority.deployment_spec_digest,
            generation=generation,
            lifecycle_state=lifecycle_state,
            observed_at=_now_rfc3339_nanos(),
            event_id=uuid6.uuid7(),
        )

    def to_wire(self) -> dict[str, Any]:
        if self.generation < 1:
            raise ValueError("lifecycle fact generation must be positive")
        if self.lifecycle_state not in _LIFECYCLE_STATES:
            raise ValueError("lifecycle fact state is invalid")
        if len(self.deployment_spec_digest) != 64:
            raise ValueError("lifecycle fact deployment spec digest must be SHA-256")
        return {
            "kind": LIFECYCLE_FACT_KIND,
            "event_id": str(self.event_id),
            "occurred_at": self.observed_at,
            "tenant_id": self.tenant_id,
            "mode": self.mode,
            "runner_id": str(self.runner_id),
            "deployment_instance_id": str(self.deployment_instance_id),
            "deployment_spec_id": str(self.deployment_spec_id),
            "deployment_spec_digest": self.deployment_spec_digest,
            "generation": self.generation,
            "lifecycle_state": self.lifecycle_state,
            "observed_at": self.observed_at,
        }


class RunnerDeploymentLifecycleFactEmitter:
    """Validate authority duplication and durably enqueue a typed lifecycle fact."""

    def __init__(
        self,
        emitter: RunnerFactEmitter,
        capability: RunnerCapabilityReceipt,
    ) -> None:
        self._emitter = emitter
        self._capability = capability

    def authority_for_spec(
        self,
        spec: Mapping[str, Any],
        *,
        strategy_id: str,
    ) -> RunnerFactAuthority:
        mode = str(spec.get("trading_mode") or "")
        instance_id = UUID(str(spec.get("deployment_instance_id")))
        spec_id = UUID(str(spec.get("spec_id")))
        strategy = UUID(strategy_id)
        digest = str(spec.get("deployment_spec_digest") or "")
        self._capability.require_scope_bindings(
            projectors=("deployment_lifecycle",),
            trading_mode=mode,
            deployment_instance_id=instance_id,
            deployment_spec_id=spec_id,
            deployment_spec_digest=digest,
            strategy_id=strategy,
        )
        return RunnerFactAuthority(
            tenant_id=self._capability.tenant_id,
            trading_mode=mode,
            runner_id=self._capability.runner_id,
            deployment_instance_id=instance_id,
            deployment_spec_id=spec_id,
            deployment_spec_digest=digest,
            strategy_id=strategy,
            capability_version_id=self._capability.capability_version_id,
            capability_version=self._capability.capability_version,
            capability_manifest_digest=self._capability.manifest_digest,
        )

    async def emit(
        self,
        authority: RunnerFactAuthority,
        *,
        generation: int,
        lifecycle_state: str,
    ) -> UUID | None:
        fact = RunnerDeploymentLifecycleFact.observed(
            authority,
            generation=generation,
            lifecycle_state=lifecycle_state,
        )
        return await self.emit_fact(authority, fact)

    async def emit_fact(
        self,
        authority: RunnerFactAuthority,
        fact: RunnerDeploymentLifecycleFact,
    ) -> UUID | None:
        if (
            fact.tenant_id != authority.tenant_id
            or fact.mode != authority.trading_mode
            or fact.runner_id != authority.runner_id
            or fact.deployment_instance_id != authority.deployment_instance_id
            or fact.deployment_spec_id != authority.deployment_spec_id
            or fact.deployment_spec_digest != authority.deployment_spec_digest
        ):
            raise ValueError("lifecycle fact authority differs from RunnerFact authority")
        self._capability.require_scope_bindings(
            projectors=("deployment_lifecycle",),
            trading_mode=authority.trading_mode,
            deployment_instance_id=authority.deployment_instance_id,
            deployment_spec_id=authority.deployment_spec_id,
            deployment_spec_digest=authority.deployment_spec_digest,
            strategy_id=authority.strategy_id,
        )
        return await self._emitter.emit(authority, (fact.to_wire(),))
