from uuid import UUID

import pytest

from custos.core.runner_deployment_lifecycle_fact import (
    LIFECYCLE_FACT_KIND,
    RunnerDeploymentLifecycleFactEmitter,
)
from custos.core.runner_fact import RunnerFactAuthority

SHA = "a" * 64


class CapturingEmitter:
    def __init__(self) -> None:
        self.facts = []

    async def emit(self, authority, facts):
        self.facts.extend(facts)


class LifecycleCapability:
    def __init__(self) -> None:
        self.projectors = None

    def require_scope_bindings(self, *, projectors, **kwargs) -> None:
        self.projectors = projectors


@pytest.mark.asyncio
async def test_lifecycle_fact_contains_complete_instance_authority() -> None:
    authority = RunnerFactAuthority(
        tenant_id="acme",
        trading_mode="sandbox",
        runner_id=UUID("10000000-0000-4000-8000-000000000001"),
        deployment_instance_id=UUID("20000000-0000-4000-8000-000000000002"),
        deployment_spec_id=UUID("30000000-0000-4000-8000-000000000003"),
        deployment_spec_digest=SHA,
        strategy_id=UUID("40000000-0000-4000-8000-000000000004"),
        capability_version_id=UUID("50000000-0000-4000-8000-000000000005"),
        capability_version=1,
        capability_manifest_digest=SHA,
    )
    capture = CapturingEmitter()
    capability = LifecycleCapability()
    await RunnerDeploymentLifecycleFactEmitter(capture, capability).emit(
        authority, generation=7, lifecycle_state="running"
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
    assert fact["observed_at"].endswith("Z")
    assert capability.projectors == ("deployment_lifecycle",)
