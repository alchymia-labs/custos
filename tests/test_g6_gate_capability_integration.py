"""G6 rejection propagated through instance-keyed reconciliation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
import structlog

from custos.core.deployment_reconciler import DeploymentReconciler
from custos.core.runner_fact import RunnerFactAuthority
from custos.engines.nautilus.strategy_loader import compute_strategy_dir_hash

SHA = "a" * 64
RUNNER_ID = UUID("10000000-0000-4000-8000-000000000001")
INSTANCE_ID = UUID("20000000-0000-4000-8000-000000000002")
SPEC_ID = UUID("30000000-0000-4000-8000-000000000003")
STRATEGY_ID = UUID("40000000-0000-4000-8000-000000000004")


class _CapabilityLessHost:
    async def deploy(self, spec: dict, credential: dict) -> str:
        return str(spec["deployment_instance_id"])

    async def reconfigure(self, spec: dict) -> None:
        return None

    async def stop(self, deployment_instance_id: str) -> None:
        return None


@pytest.fixture
def strategy_dir(tmp_path):
    directory = tmp_path / "supertrend"
    directory.mkdir()
    (directory / "strategy.py").write_text("class SupertrendStrategy:\n    pass\n")
    return directory


def _live_spec(strategy_dir) -> dict:
    return {
        "spec_id": str(SPEC_ID),
        "deployment_instance_id": str(INSTANCE_ID),
        "deployment_spec_digest": SHA,
        "strategy_id": str(STRATEGY_ID),
        "generation": 1,
        "trading_mode": "live",
        "lifecycle_state": "running",
        "connector": "binance_perpetual",
        "pairs": ["BTC-USDT"],
        "leverage": 1,
        "strategy_path": str(strategy_dir / "strategy.py"),
        "strategy_config": {},
        "code_hash": compute_strategy_dir_hash(strategy_dir),
        "provenance_ref": {"credential_id": "cred-live"},
        "promotion_id": "50000000-0000-4000-8000-000000000005",
        "promotion_evidence_digest": "b" * 64,
    }


def _authority(value: dict, *, strategy_id: str) -> RunnerFactAuthority:
    return RunnerFactAuthority(
        tenant_id="acme",
        trading_mode=value["trading_mode"],
        runner_id=RUNNER_ID,
        deployment_instance_id=UUID(value["deployment_instance_id"]),
        deployment_spec_id=UUID(value["spec_id"]),
        deployment_spec_digest=value["deployment_spec_digest"],
        strategy_id=UUID(strategy_id),
        capability_version_id=UUID("60000000-0000-4000-8000-000000000006"),
        capability_version=1,
        capability_manifest_digest=SHA,
    )


def _reconciler(host) -> tuple[DeploymentReconciler, MagicMock, MagicMock]:
    vault = MagicMock()
    vault.decrypt.return_value = {
        "api_key": "k",
        "api_secret": "s",
        "permission_scope": "trade_no_withdraw",
    }
    runtime_log = MagicMock()
    runtime_log.authority_for_spec.side_effect = _authority
    runtime_log.emit = AsyncMock()
    lifecycle = MagicMock()
    lifecycle.authority_for_spec.side_effect = _authority
    lifecycle.emit_fact = AsyncMock()
    subject = DeploymentReconciler(
        nats_client=object(),  # type: ignore[arg-type]
        tenant_id="acme",
        runner_id=str(RUNNER_ID),
        execution_engine=host,
        credential_vault=vault,
        runtime_log_emitter=runtime_log,
        lifecycle_fact_emitter=lifecycle,
        deployment_verifier=object(),  # type: ignore[arg-type]
    )
    return subject, runtime_log, lifecycle


@pytest.mark.asyncio
async def test_undeclared_host_degrades_without_emitting_applied_fact(strategy_dir) -> None:
    reconciler, runtime_log, lifecycle = _reconciler(_CapabilityLessHost())

    with structlog.testing.capture_logs() as logs:
        applied = await reconciler.handle_spec(_live_spec(strategy_dir))

    assert applied is False
    events = [entry.get("event") for entry in logs]
    assert "g6_gate_live_capability_denied" in events
    assert "deployment_reconcile_failed" in events
    runtime_log.emit.assert_awaited_once()
    lifecycle.emit_fact.assert_not_awaited()
