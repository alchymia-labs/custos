"""Inbound-only JetStream transport for Crucible deployment commands.

Custos observations leave through the signed RunnerFact outbox. This client has
no unsigned telemetry, DeploymentStatus, snapshot, or ARX business-topic
publication surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from custos.core.runner_command_intake import CommandDeliveryPolicy

try:  # pragma: no cover - production dependency, mocked by unit tests
    import nats
    from nats.js.api import AckPolicy, ConsumerConfig
except ImportError as exc:  # pragma: no cover
    nats = None  # type: ignore[assignment]
    AckPolicy = None  # type: ignore[assignment,misc]
    ConsumerConfig = None  # type: ignore[assignment,misc]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


@dataclass
class CrucibleNatsClient:
    nats_url: str
    tenant_id: str
    runner_id: str
    machine_credential: Any = field(repr=False)
    command_delivery_policy: CommandDeliveryPolicy = field(default_factory=CommandDeliveryPolicy)
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
        subject = f"crucible_rust.domain.{self.tenant_id}.*.deployment.*.{self.runner_id}.*"
        durable = f"custos-deployment-{self.runner_id}"
        consumer_config = ConsumerConfig(
            durable_name=durable,
            ack_policy=AckPolicy.EXPLICIT,
            ack_wait=self.command_delivery_policy.ack_wait_seconds,
            max_deliver=self.command_delivery_policy.max_deliver,
            backoff=list(self.command_delivery_policy.backoff_seconds),
            filter_subject=subject,
        )
        return await self._js.subscribe(
            subject,
            durable=durable,
            config=consumer_config,
            manual_ack=True,
        )
