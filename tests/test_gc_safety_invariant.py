"""GC-safety invariant — fire-and-forget tasks are strongly referenced in-flight.

``asyncio.create_task`` / ``ensure_future`` return a task the event loop only
weakly holds; drop the reference and the loop may GC it mid-run, silently losing
whatever it was doing. Three runner sites schedule such tasks and each must keep
a strong reference until the task finishes (对账不静默 红线 — a dropped publish /
drain / actor-teardown is a silent loss):

* ``NtRiskEngineBridge._pending`` — in-flight pre-trade-reject publishes
* ``NtTradingNodeHost._cleanup_tasks`` — self-terminated node actor teardowns
* ``ArxNatsClient._wal_drain_task`` — the offline-WAL replay task

Each set/attr holds the task in-flight and the done-callback removes it after,
so the reference is live exactly as long as the task is (no leak, no GC drop).
None of these sites need NautilusTrader, so this runs on a base install.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from arx_runner import nats_client as nats_client_mod
from arx_runner.nats_client import ArxNatsClient
from arx_runner.nautilus_host import NtTradingNodeHost
from arx_runner.nt_risk_engine import NtRiskEngineBridge


class _FakeActor:
    async def stop(self) -> None:
        return None


async def test_nt_risk_engine_pending_discards_after_await() -> None:
    client = ArxNatsClient(nats_url="nats://x", tenant_id="acme", runner_id="r7")
    fake_js = MagicMock()
    fake_js.publish = AsyncMock()
    client._js = fake_js
    bridge = NtRiskEngineBridge(client=client, tenant_id="acme", runner_id="r7")

    class OrderDenied:  # NT-typed event: the dispatcher filters by type name
        reason = "MAX_NOTIONAL exceeded"
        instrument_id = "BTCUSDT"

    bridge._on_order_event(OrderDenied())
    # In-flight: the scheduled publish future is strongly referenced.
    assert len(bridge._pending) == 1
    fut = next(iter(bridge._pending))

    await fut
    await asyncio.sleep(0)  # let the done-callback run
    # Discarded once done — the reference is live exactly as long as the task.
    assert len(bridge._pending) == 0


async def test_nautilus_host_cleanup_tasks_discards_after_await() -> None:
    host = NtTradingNodeHost()
    task = asyncio.ensure_future(asyncio.sleep(0))
    await task  # a self-terminated node loop (completed)

    host._active_nodes["spec-b"] = (object(), task)
    host._telemetry_actors["spec-b"] = _FakeActor()
    host._on_node_task_done("spec-b", task)

    # In-flight: the actor-teardown task is strongly referenced.
    assert len(host._cleanup_tasks) == 1
    cleanup = next(iter(host._cleanup_tasks))

    await cleanup
    await asyncio.sleep(0)  # let the discard callback run
    assert len(host._cleanup_tasks) == 0


async def test_nats_client_wal_drain_task_strong_referenced(monkeypatch) -> None:
    fake_js = MagicMock()
    fake_nc = MagicMock()
    fake_nc.jetstream = MagicMock(return_value=fake_js)
    monkeypatch.setattr(nats_client_mod.nats, "connect", AsyncMock(return_value=fake_nc))

    client = ArxNatsClient(nats_url="nats://x", tenant_id="acme", runner_id="r7")
    assert client._wal_drain_task is None  # not scheduled until connect

    await client.connect()

    # The WAL-drain task is held on the client, not left GC-droppable.
    assert client._wal_drain_task is not None
    assert isinstance(client._wal_drain_task, asyncio.Task)
    await client._wal_drain_task  # no wal_path → returns immediately
