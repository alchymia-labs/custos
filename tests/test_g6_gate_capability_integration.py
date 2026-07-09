"""G6 undeclared-capability rejection propagated through the reconciler layer.

test_g6_gate_capability_e2e.py drives ``_check_g6_gate`` directly to isolate one
gate layer. This file drives the *integration* layer — ``handle_spec`` — to prove
the gate's structured rejection does not stop at the gate: it degrades the
deployment (DeploymentStatus phase=degraded) without breaking the reconcile loop
(the broad except is red-line-0.3 fail-safe: a rejected spec must not crash the
loop that keeps other deployments alive).

Two independently observable layers, each asserted (multi-layer fail-fast, lesson
#22/#28): the inner gate layer emits ``g6_gate_live_capability_denied``; the outer
reconciler wrapper emits ``deployment_reconcile_failed`` and publishes a degraded
status. ``_CapabilityLessHost`` is the relaxed double — a host that never declared
the capability contract — so a green result proves the reconciler-layer
degradation is a live guard, not a dead branch.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog

from arx_runner._strategy_loader import compute_strategy_dir_hash
from arx_runner.deployment_reconciler import DeploymentReconciler


class _CapabilityLessHost:
    """Satisfies deploy/reconfigure/stop but never declared supports_live /
    supports_venue — a third-party host that forgot the capability contract."""

    async def deploy(self, spec: dict, credential: dict) -> str:
        return str(spec["spec_id"])

    async def reconfigure(self, spec: dict) -> None:
        return None

    async def stop(self, spec_id: str) -> None:
        return None


@pytest.fixture
def strategy_dir(tmp_path):
    d = tmp_path / "supertrend"
    d.mkdir()
    (d / "strategy.py").write_text("class SupertrendStrategy:\n    pass\n")
    return d


def _live_spec(strategy_dir) -> dict:
    return {
        "spec_id": "live-int-1",
        "generation": 1,
        "trading_mode": "live",
        "connector": "binance_perpetual",
        "strategy_path": str(strategy_dir / "strategy.py"),
        "code_hash": compute_strategy_dir_hash(strategy_dir),
    }


def _reconciler(host) -> tuple[DeploymentReconciler, MagicMock]:
    nats_client = MagicMock()
    nats_client.publish_deployment_status = AsyncMock()
    vault = MagicMock()
    vault.decrypt.return_value = {
        "api_key": "k",
        "api_secret": "s",
        "permission_scope": "trade_no_withdraw",
    }
    reconciler = DeploymentReconciler(
        nats_client=nats_client,
        tenant_id="acme",
        runner_id="runner-7",
        nautilus_host=host,
        credential_vault=vault,
    )
    return reconciler, nats_client


async def test_undeclared_host_at_reconciler_layer_degrades(strategy_dir) -> None:
    reconciler, nats_client = _reconciler(_CapabilityLessHost())

    with structlog.testing.capture_logs() as logs:
        # Must not raise — the broad except keeps the reconcile loop alive.
        await reconciler.handle_spec(_live_spec(strategy_dir))

    events = [e.get("event") for e in logs]
    # Inner gate layer signalled the structured capability rejection...
    assert "g6_gate_live_capability_denied" in events
    # ...and the outer reconciler wrapper degraded rather than propagating.
    assert "deployment_reconcile_failed" in events

    nats_client.publish_deployment_status.assert_awaited_once()
    payload = nats_client.publish_deployment_status.call_args.kwargs["payload"]
    assert payload["phase"] == "degraded"
    assert payload["health"] == "unhealthy"
