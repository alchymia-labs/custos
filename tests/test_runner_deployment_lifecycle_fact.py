from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, cast
from uuid import UUID

import pytest

from custos.core.runner_deployment_lifecycle_fact import (
    LIFECYCLE_FACT_KIND,
    RunnerDeploymentLifecycleFact,
    RunnerDeploymentLifecycleFactEmitter,
)
from custos.core.runner_fact import RunnerFactAuthority, RunnerFactEmitter

SHA = "a" * 64
FINGERPRINT = "b" * 64


class CapturingEmitter:
    def __init__(self) -> None:
        self.facts: list[dict[str, Any]] = []

    async def emit(
        self,
        authority: RunnerFactAuthority,
        facts: Sequence[Mapping[str, Any]],
    ) -> None:
        del authority
        self.facts.extend(dict(fact) for fact in facts)


@pytest.mark.asyncio
async def test_lifecycle_fact_contains_complete_instance_authority() -> None:
    authority = RunnerFactAuthority(
        tenant_id="acme",
        trading_mode="sandbox",
        runner_id=UUID("10000000-0000-4000-8000-000000000001"),
        deployment_instance_id=UUID("20000000-0000-4000-8000-000000000002"),
        deployment_spec_id=UUID("30000000-0000-4000-8000-000000000003"),
        deployment_spec_digest=SHA,
        generation=7,
        strategy_id=UUID("40000000-0000-4000-8000-000000000004"),
        capability_version_id=UUID("50000000-0000-4000-8000-000000000005"),
        capability_version=1,
        capability_manifest_digest=SHA,
    )
    capture = CapturingEmitter()
    from pathlib import Path

    from custos.core.runner_fact import RunnerCapabilityReceipt

    capability = RunnerCapabilityReceipt.load(
        Path(__file__).parents[1] / "docs/authority/runner-fact-capability-receipt-golden-v1.json"
    )
    await RunnerDeploymentLifecycleFactEmitter(cast(RunnerFactEmitter, capture), capability).emit(
        authority,
        generation=7,
        lifecycle_state="running",
        command_fingerprint=FINGERPRINT,
        outcome="applied",
    )
    fact = capture.facts[0]
    assert fact["kind"] == LIFECYCLE_FACT_KIND
    assert fact["tenant_id"] == "acme"
    assert fact["mode"] == "sandbox"
    assert fact["deployment_instance_id"] == str(authority.deployment_instance_id)
    assert fact["deployment_spec_id"] == str(authority.deployment_spec_id)
    assert fact["deployment_spec_digest"] == SHA
    assert fact["generation"] == 7
    assert fact["lifecycle_state"] == "running"
    assert fact["command_fingerprint"] == FINGERPRINT
    assert fact["outcome"] == "applied"
    assert fact["observed_at"].endswith("Z")


def _authority() -> RunnerFactAuthority:
    return RunnerFactAuthority(
        tenant_id="acme",
        trading_mode="sandbox",
        runner_id=UUID("10000000-0000-4000-8000-000000000001"),
        deployment_instance_id=UUID("20000000-0000-4000-8000-000000000002"),
        deployment_spec_id=UUID("30000000-0000-4000-8000-000000000003"),
        deployment_spec_digest=SHA,
        generation=7,
        strategy_id=UUID("40000000-0000-4000-8000-000000000004"),
        capability_version_id=UUID("50000000-0000-4000-8000-000000000005"),
        capability_version=1,
        capability_manifest_digest=SHA,
    )


def test_lifecycle_event_identity_survives_retry_restart_and_observation_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = _authority()
    observed_times = iter(("2026-07-15T08:00:00.000000000Z", "2026-07-15T08:01:00.000000000Z"))
    monkeypatch.setattr(
        "custos.core.runner_deployment_lifecycle_fact._now_rfc3339_nanos",
        lambda: next(observed_times),
    )

    first = RunnerDeploymentLifecycleFact.observed(
        authority,
        generation=7,
        lifecycle_state="running",
        command_fingerprint=FINGERPRINT,
        outcome="applied",
    )
    restarted = RunnerDeploymentLifecycleFact.observed(
        authority,
        generation=7,
        lifecycle_state="running",
        command_fingerprint=FINGERPRINT,
        outcome="applied",
    )

    assert first.observed_at != restarted.observed_at
    assert first.event_id == restarted.event_id


@pytest.mark.parametrize(
    ("authority_change", "generation", "state", "fingerprint", "outcome"),
    [
        ({"tenant_id": "other-tenant"}, 7, "running", FINGERPRINT, "applied"),
        ({"trading_mode": "testnet"}, 7, "running", FINGERPRINT, "applied"),
        (
            {"runner_id": UUID("10000000-0000-4000-8000-000000000099")},
            7,
            "running",
            FINGERPRINT,
            "applied",
        ),
        (
            {"deployment_instance_id": UUID("20000000-0000-4000-8000-000000000099")},
            7,
            "running",
            FINGERPRINT,
            "applied",
        ),
        (
            {"deployment_spec_id": UUID("30000000-0000-4000-8000-000000000099")},
            7,
            "running",
            FINGERPRINT,
            "applied",
        ),
        ({"deployment_spec_digest": "c" * 64}, 7, "running", FINGERPRINT, "applied"),
        ({}, 8, "running", FINGERPRINT, "applied"),
        ({}, 7, "paused", FINGERPRINT, "applied"),
        ({}, 7, "running", "d" * 64, "applied"),
        ({}, 7, "running", FINGERPRINT, "conflict"),
    ],
)
def test_lifecycle_event_identity_changes_with_each_stable_identity_component(
    authority_change: dict[str, Any],
    generation: int,
    state: str,
    fingerprint: str,
    outcome: str,
) -> None:
    authority = _authority()
    baseline = RunnerDeploymentLifecycleFact.observed(
        authority,
        generation=7,
        lifecycle_state="running",
        command_fingerprint=FINGERPRINT,
        outcome="applied",
    )
    changed_authority = replace(authority, **authority_change)
    changed = RunnerDeploymentLifecycleFact.observed(
        changed_authority,
        generation=generation,
        lifecycle_state=state,
        command_fingerprint=fingerprint,
        outcome=outcome,
    )

    assert changed.event_id != baseline.event_id
