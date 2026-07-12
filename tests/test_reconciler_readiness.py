from __future__ import annotations

import asyncio
import json
import stat
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock

from custos.cli.subcommands import main
from custos.core.deployment_reconciler import DeploymentReconciler
from custos.core.readiness import ReadinessFile


class _IdleSubscription:
    async def next_msg(self, timeout: float):
        await asyncio.sleep(timeout * 10)


class _LostSubscription:
    async def next_msg(self, timeout: float):
        raise ConnectionError("subscription lost")


@dataclass
class _RetryNats:
    failures: int
    subscription: object = field(default_factory=_IdleSubscription)
    attempts: int = 0

    async def subscribe_deployment_spec(self, *, strategy_id: str):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise ConnectionError("not ready")
        return self.subscription


@dataclass
class _ReadinessSpy:
    marks: list[dict] = field(default_factory=list)
    clear_count: int = 0

    def mark_ready(self, **state) -> None:
        self.marks.append(state)

    def clear(self) -> None:
        self.clear_count += 1


class _Engine:
    pass


class _Vault:
    pass


def _reconciler(nats_client, readiness) -> DeploymentReconciler:
    return DeploymentReconciler(
        nats_client=nats_client,
        tenant_id="acme",
        runner_id="runner-1",
        execution_engine=_Engine(),  # type: ignore[arg-type]
        credential_vault=_Vault(),  # type: ignore[arg-type]
        readiness=readiness,
        poll_interval_secs=0.005,
        subscribe_backoff_initial_secs=0.005,
        subscribe_backoff_max_secs=0.01,
    )


async def _wait_until(predicate, timeout: float = 0.5) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.001)


async def test_initial_subscribe_failure_retries() -> None:
    nats_client = _RetryNats(failures=2)
    readiness = _ReadinessSpy()
    reconciler = _reconciler(nats_client, readiness)
    stop = asyncio.Event()
    task = asyncio.create_task(reconciler.reconcile_loop(stop, "strategy-1"))

    await _wait_until(lambda: bool(readiness.marks))
    stop.set()
    await task

    assert nats_client.attempts == 3


async def test_local_guards_tick_while_subscription_is_down() -> None:
    reconciler = _reconciler(_RetryNats(failures=10_000), _ReadinessSpy())
    reconciler._watchdog_tick = AsyncMock()  # type: ignore[method-assign]
    reconciler._breaker_tick = AsyncMock()  # type: ignore[method-assign]
    stop = asyncio.Event()
    task = asyncio.create_task(reconciler.reconcile_loop(stop, "strategy-1"))

    await _wait_until(lambda: reconciler._watchdog_tick.await_count >= 3)
    stop.set()
    await task

    assert reconciler._breaker_tick.await_count >= 3


async def test_subscription_recovery_marks_ready() -> None:
    readiness = _ReadinessSpy()
    reconciler = _reconciler(_RetryNats(failures=1), readiness)
    stop = asyncio.Event()
    task = asyncio.create_task(reconciler.reconcile_loop(stop, "strategy-1"))

    await _wait_until(lambda: bool(readiness.marks))
    stop.set()
    await task

    assert readiness.marks[0] == {
        "strategy_id": "strategy-1",
        "nats_connected": True,
        "deployment_subscription": True,
    }


async def test_subscription_loss_clears_ready() -> None:
    readiness = _ReadinessSpy()
    nats_client = _RetryNats(failures=0, subscription=_LostSubscription())
    reconciler = _reconciler(nats_client, readiness)
    stop = asyncio.Event()
    task = asyncio.create_task(reconciler.reconcile_loop(stop, "strategy-1"))

    await _wait_until(lambda: len(readiness.marks) >= 2)
    stop.set()
    await task

    assert readiness.clear_count >= 2


async def test_stop_interrupts_backoff() -> None:
    reconciler = _reconciler(_RetryNats(failures=10_000), _ReadinessSpy())
    reconciler.subscribe_backoff_initial_secs = 5.0
    reconciler.subscribe_backoff_max_secs = 5.0
    stop = asyncio.Event()
    task = asyncio.create_task(reconciler.reconcile_loop(stop, "strategy-1"))
    await _wait_until(lambda: reconciler.nats_client.attempts >= 1)

    stop.set()
    await asyncio.wait_for(task, timeout=0.1)


def test_health_fails_before_ready(tmp_path: Path) -> None:
    ready_file = tmp_path / "runner-ready.json"

    assert main(["health", "--ready-file", str(ready_file)]) != 0


def test_health_rejects_incomplete_ready_state(tmp_path: Path) -> None:
    ready_file = tmp_path / "runner-ready.json"
    ready_file.write_text(
        json.dumps(
            {
                "ready": True,
                "nats_connected": True,
                "deployment_subscription": False,
            }
        )
    )

    assert main(["health", "--ready-file", str(ready_file)]) != 0


def test_health_passes_after_atomic_ready_write(tmp_path: Path) -> None:
    ready_file = tmp_path / "state" / "runner-ready.json"
    readiness = ReadinessFile(ready_file, tenant_id="acme", runner_id="runner-1")

    readiness.mark_ready(
        strategy_id="strategy-1",
        nats_connected=True,
        deployment_subscription=True,
    )

    assert main(["health", "--ready-file", str(ready_file)]) == 0
    assert stat.S_IMODE(ready_file.stat().st_mode) == 0o600
    assert json.loads(ready_file.read_text()) == {
        "ready": True,
        "tenant_id": "acme",
        "runner_id": "runner-1",
        "strategy_id": "strategy-1",
        "nats_connected": True,
        "deployment_subscription": True,
    }
    assert list(ready_file.parent.glob("*.tmp")) == []
