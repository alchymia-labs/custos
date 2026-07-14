"""Inbound-only Crucible deployment transport authority tests."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from custos.core.nats_client import CrucibleNatsClient

_RUNNER_ID = UUID("22222222-2222-4222-8222-222222222222")


@dataclass
class _MachineCredential:
    tenant_id: str = "acme"
    runner_id: UUID = _RUNNER_ID
    active: bool = True

    def assert_active(self) -> None:
        if not self.active:
            raise RuntimeError("machine credential is inactive")


def _client(credential: _MachineCredential | None = None) -> CrucibleNatsClient:
    return CrucibleNatsClient(
        nats_url="nats://localhost:4222",
        tenant_id="acme",
        runner_id=str(_RUNNER_ID),
        machine_credential=credential or _MachineCredential(),
    )


def test_client_rejects_machine_authority_binding_mismatch() -> None:
    credential = _MachineCredential(tenant_id="other-tenant")
    with pytest.raises(ValueError, match="authority does not match"):
        _client(credential)


def test_client_rejects_inactive_machine_credential() -> None:
    with pytest.raises(RuntimeError, match="inactive"):
        _client(_MachineCredential(active=False))


@pytest.mark.asyncio
async def test_subscribe_uses_crucible_runner_scoped_subject_and_durable() -> None:
    client = _client()
    subscription = object()
    jetstream = MagicMock()
    jetstream.subscribe = AsyncMock(return_value=subscription)
    client._js = jetstream

    result = await client.subscribe_deployment_spec()

    assert result is subscription
    jetstream.subscribe.assert_awaited_once_with(
        f"crucible_rust.domain.acme.*.deployment.*.{_RUNNER_ID}.*",
        durable=f"custos-deployment-{_RUNNER_ID}",
        manual_ack=True,
    )


@pytest.mark.asyncio
async def test_subscribe_before_connect_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="before connect"):
        await _client().subscribe_deployment_spec()
