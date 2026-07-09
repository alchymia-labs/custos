"""ArxNatsClient.publish_heartbeat targets the canonical subject.

Subject grammar (plan-index §6):
    arx.{tenant}.heartbeat.{runner_id}

Delivery semantics: at-most-once, fire-and-forget (no ack expected).
We mock the JetStream context so the test runs without a live NATS server.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from custos.core.nats_client import ArxNatsClient


@pytest.mark.asyncio
async def test_publish_heartbeat_uses_canonical_subject_and_envelope() -> None:
    client = ArxNatsClient(
        nats_url="nats://localhost:4222",
        tenant_id="acme",
        runner_id="runner-7",
    )

    # Heartbeat delivery is at-most-once fire-and-forget through core NATS
    # (`self._nc.publish`), not JetStream — so we mock `_nc`, not `_js`. The
    # disconnect branch keys on `_nc is None` and emits
    # `nats_fire_and_forget_noop_disconnected` (lesson #21 zero-silent);
    # mocking the wrong attribute would trip that branch and silently pass
    # a stale contract.
    fake_nc = MagicMock()
    fake_nc.publish = AsyncMock()
    client._nc = fake_nc  # bypass real connect for unit test

    await client.publish_heartbeat(
        health="ok",
        seq=3,
        session_id="22222222-2222-2222-2222-222222222222",
        uptime_secs=42,
        active_deployments=1,
    )

    fake_nc.publish.assert_awaited_once()
    args, kwargs = fake_nc.publish.call_args
    subject = args[0] if args else kwargs["subject"]
    payload = args[1] if len(args) > 1 else kwargs["payload"]

    assert subject == "arx.acme.heartbeat.runner-7"

    decoded = json.loads(payload)
    assert decoded["tenant_id"] == "acme"
    assert decoded["payload"]["health"] == "ok"
    assert decoded["payload"]["runner_id"] == "runner-7"
    assert decoded["payload"]["uptime_secs"] == 42
    assert decoded["payload"]["active_deployments"] == 1
    assert decoded["ordering"]["session_id"] == "22222222-2222-2222-2222-222222222222"
    assert decoded["ordering"]["seq"] == 3
