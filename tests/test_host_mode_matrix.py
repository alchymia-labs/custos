"""Non-live host matrix reported through signed lifecycle facts."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from custos.core.deployment_reconciler import DeploymentReconciler
from custos.core.runner_fact import RunnerFactAuthority
from custos.engines.nautilus import host as nautilus_host
from custos.engines.nautilus.host import NoopHost, NtTradingNodeHost
from custos.engines.nautilus.strategy_loader import compute_strategy_dir_hash

SHA = "a" * 64
RUNNER_ID = UUID("10000000-0000-4000-8000-000000000001")
SPEC_ID = UUID("30000000-0000-4000-8000-000000000003")
STRATEGY_ID = UUID("40000000-0000-4000-8000-000000000004")
INSTANCE_BY_MODE = {
    "sandbox": UUID("20000000-0000-4000-8000-000000000002"),
    "testnet": UUID("21000000-0000-4000-8000-000000000002"),
}


class _FakeTrader:
    def add_strategy(self, strategy) -> None:
        return None


class _FakeNode:
    def __init__(self, config) -> None:
        self.config = config
        self.trader = _FakeTrader()
        self.kernel = MagicMock()
        self._stop = asyncio.Event()

    def add_data_client_factory(self, name, factory) -> None:
        return None

    def add_exec_client_factory(self, name, factory) -> None:
        return None

    def build(self) -> None:
        return None

    async def run_async(self) -> None:
        await self._stop.wait()

    async def stop_async(self) -> None:
        self._stop.set()

    def dispose(self) -> None:
        return None


@pytest.fixture
def strategy_dir(tmp_path):
    directory = tmp_path / "matrix"
    directory.mkdir()
    (directory / "strategy.py").write_text("class MatrixStrategy:\n    pass\n")
    return directory


def _matrix_spec(mode: str, strategy_dir) -> dict:
    value = {
        "spec_id": str(SPEC_ID),
        "deployment_instance_id": str(INSTANCE_BY_MODE[mode]),
        "deployment_spec_digest": SHA,
        "strategy_id": str(STRATEGY_ID),
        "generation": 1,
        "trading_mode": mode,
        "lifecycle_state": "running",
        "connector": "binance_perpetual",
        "pairs": ["BTC-USDT"],
        "leverage": 1,
        "strategy_path": str(strategy_dir / "strategy.py"),
        "strategy_config": {},
        "code_hash": compute_strategy_dir_hash(strategy_dir),
        "provenance_ref": {"credential_id": "cred-matrix"},
    }
    if mode == "sandbox":
        value["sandbox"] = {"starting_balances": ["10_000 USDT"]}
    return value


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


def _reconciler(host) -> tuple[DeploymentReconciler, MagicMock]:
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
    return subject, lifecycle


@pytest.mark.parametrize(
    ("mode", "host_kind"),
    [
        pytest.param("sandbox", "NoopHost", id="sandbox-NoopHost"),
        pytest.param("sandbox", "NtTradingNodeHost", id="sandbox-NtTradingNodeHost"),
        pytest.param("testnet", "NoopHost", id="testnet-NoopHost"),
        pytest.param("testnet", "NtTradingNodeHost", id="testnet-NtTradingNodeHost"),
    ],
)
@pytest.mark.asyncio
async def test_mode_host_matrix(mode, host_kind, strategy_dir, monkeypatch) -> None:
    if host_kind == "NoopHost":
        host = NoopHost()
    else:
        pytest.importorskip("nautilus_trader")
        monkeypatch.setattr(nautilus_host, "TradingNode", _FakeNode)
        host = NtTradingNodeHost()

    reconciler, lifecycle = _reconciler(host)
    spec = _matrix_spec(mode, strategy_dir)
    try:
        assert await reconciler.handle_spec(spec) is True
        lifecycle.emit_fact.assert_awaited_once()
        assert reconciler._state[spec["deployment_instance_id"]].applied_generation == 1
    finally:
        await host.stop(spec["deployment_instance_id"])
