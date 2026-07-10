"""Runner entry-point wires the state snapshot publisher (04b-fix HIGH-1).

The 04b squash-merge shipped ``StateSnapshotPublisher`` (``core/state_snapshot.py``)
but the runner entry point (``cli/main.py``) never constructed or started it, so
a real deployment published zero snapshots at runtime. This test locks in that
``_run`` schedules ``publisher.run()`` alongside the reconciler + heartbeat when
``--reconcile-strategy-id`` is set.

The publisher is spec-scoped; it iterates ``reconciler.active_spec_ids()`` on
each interval so a runner running N concurrent deployments still publishes one
snapshot per active spec.
"""

from __future__ import annotations

import asyncio
import os
import signal

import pytest

from custos.cli import main as cli_main
from custos.core.deployment_reconciler import DeploymentReconciler


class _StubNatsClient:
    """Replaces ``ArxNatsClient`` so the entry point never touches a broker."""

    def __init__(self, *args, **kwargs) -> None:
        self.connect_called = False
        self.close_called = False

    async def connect(self) -> None:
        self.connect_called = True

    async def close(self) -> None:
        self.close_called = True


class _StubReconciler:
    """Replaces ``DeploymentReconciler`` so ``reconcile_loop`` just awaits stop."""

    def __init__(self, *args, **kwargs) -> None:
        self._active: list[str] = []
        self.reconcile_calls: list[str] = []

    def active_spec_ids(self) -> list[str]:
        return list(self._active)

    async def reconcile_loop(self, stop: asyncio.Event, strategy_id: str) -> None:
        self.reconcile_calls.append(strategy_id)
        await stop.wait()


class _StubPublisher:
    """Replaces ``StateSnapshotPublisher`` capturing constructor + ``run`` calls."""

    instances: list[_StubPublisher] = []

    def __init__(self, *, engine, nats_client, tenant_id, runner_id, interval_secs, **_):
        self.engine = engine
        self.nats_client = nats_client
        self.tenant_id = tenant_id
        self.runner_id = runner_id
        self.interval_secs = interval_secs
        self.run_calls: list[list[str]] = []
        type(self).instances.append(self)

    async def run(self, stop: asyncio.Event, spec_id_source) -> None:
        # Record what spec_id source we were given, then await stop so the test
        # controls the loop lifecycle deterministically.
        self.run_calls.append(list(spec_id_source()))
        await stop.wait()


async def test_reconciler_exposes_active_spec_ids() -> None:
    """The publisher needs to know which specs are currently deployed. Expose
    a public ``active_spec_ids`` method on the reconciler so we don't reach
    into private ``_state`` from the composition root."""

    reconciler = DeploymentReconciler(
        nats_client=object(),  # type: ignore[arg-type]
        tenant_id="t",
        runner_id="r",
        execution_engine=object(),  # type: ignore[arg-type]
        credential_vault=object(),  # type: ignore[arg-type]
    )
    # Empty when no spec deployed.
    assert reconciler.active_spec_ids() == []

    # Populate two specs — one deployed (has container_id), one not.
    from custos.core.deployment_reconciler import _ReconcileState

    reconciler._state["s-1"] = _ReconcileState(container_id="c-1", observed_generation=1)
    reconciler._state["s-2"] = _ReconcileState(container_id=None, observed_generation=0)

    assert reconciler.active_spec_ids() == ["s-1"]


@pytest.mark.asyncio
async def test_main_starts_state_snapshot_publisher(monkeypatch, tmp_path) -> None:
    """When ``--reconcile-strategy-id`` is set, ``_run`` must schedule the
    state snapshot publisher alongside the reconciler + heartbeat. Without
    this wire, snapshots ship zero at runtime (04b codex HIGH-1)."""

    _StubPublisher.instances.clear()

    monkeypatch.setattr(cli_main, "ArxNatsClient", _StubNatsClient)
    monkeypatch.setattr(cli_main, "DeploymentReconciler", _StubReconciler)
    monkeypatch.setattr(cli_main, "StateSnapshotPublisher", _StubPublisher)

    # Skip vault construction — it tries to read files. A minimal MockVault
    # comes back from CredentialVault(tenant_id=..., initiator=...) but we
    # keep the arg path clean by not providing sops/age flags.

    # Short-circuit the heartbeat loop so the test doesn't need to wait one
    # heartbeat interval. Replace with a task that awaits the stop event.
    async def _fake_heartbeat(client, interval, stop):
        await stop.wait()

    monkeypatch.setattr(cli_main, "_heartbeat_loop", _fake_heartbeat)

    args = cli_main._parse_args(
        [
            "--tenant-id",
            "acme",
            "--runner-id",
            "runner-1",
            "--reconcile-strategy-id",
            "strat-1",
            "--wal-path",
            str(tmp_path / "wal.db"),
        ]
    )

    # Kick off _run and stop it shortly — long enough that background tasks
    # have started but short enough not to block the suite.
    async def _stop_soon() -> None:
        await asyncio.sleep(0.05)
        # SIGTERM triggers the stop event installed by _run.
        os.kill(os.getpid(), signal.SIGTERM)

    stop_task = asyncio.create_task(_stop_soon())
    rc = await cli_main._run(args)
    await stop_task
    assert rc == 0

    # The publisher was constructed exactly once and its run() was invoked
    # (proving the wire, not just the import).
    assert len(_StubPublisher.instances) == 1
    inst = _StubPublisher.instances[0]
    assert inst.tenant_id == "acme"
    assert inst.runner_id == "runner-1"
    assert inst.run_calls, "publisher.run() must be scheduled by the runner entry point"
