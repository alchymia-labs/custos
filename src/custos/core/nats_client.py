"""Inbound-only JetStream transport for Crucible deployment commands.

Custos observations leave through the signed RunnerFact outbox. This client has
no unsigned telemetry, DeploymentStatus, snapshot, or ARX business-topic
publication surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:  # pragma: no cover - production dependency, mocked by unit tests
    import nats
except ImportError as exc:  # pragma: no cover
    nats = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


@dataclass
class CrucibleNatsClient:
    nats_url: str
    tenant_id: str
    runner_id: str
    machine_credential: Any = field(repr=False)
    _nc: Any = field(default=None, init=False, repr=False)
    _js: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.machine_credential.assert_active()
        if (
            self.machine_credential.tenant_id != self.tenant_id
            or str(self.machine_credential.runner_id) != self.runner_id
        ):
            raise ValueError("NATS machine authority does not match tenant/runner binding")

    async def connect(self) -> None:
        if nats is None:  # pragma: no cover
            raise RuntimeError(f"nats-py is not installed: {_IMPORT_ERROR}")
        self._nc = await nats.connect(self.nats_url)
        self._js = self._nc.jetstream()

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()
        self._nc = None
        self._js = None

    async def subscribe_deployment_spec(self) -> Any:
        """Subscribe to initial and subsequent exact-runner desired-state events."""
        if self._js is None:
            raise RuntimeError("subscribe_deployment_spec called before connect()")
        subject = (
            f"crucible_rust.domain.{self.tenant_id}.*.deployment."
            f"*.{self.runner_id}.*"
        )
        durable = f"custos-deployment-{self.runner_id}"
        return await self._js.subscribe(subject, durable=durable, manual_ack=True)
