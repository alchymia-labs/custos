"""Host × trading_mode selection matrix — the four non-live cells.

``--use-nt-host`` × ``spec.trading_mode`` is a 6-cell space (sandbox / testnet /
live × NoopHost / NtTradingNodeHost). The two live cells are covered elsewhere
and cross referenced rather than duplicated:

* live × NoopHost — test_g6_gate.py::test_g6_gate_rejects_live_noophost (layer-1 reject)
* live × NtTradingNodeHost — test_g6_gate.py::test_g6_gate_allows_live_nt_host (all layers pass)

This file fills the remaining four: sandbox / testnet × {NoopHost,
NtTradingNodeHost}. Each is non-live, so the G6 gate bypasses and the deploy is
admitted; the reconciler reports a running / healthy DeploymentStatus. The
NtTradingNodeHost cells assemble the real Binance venue configs (sandbox
SandboxLiveExecClientFactory / testnet BinanceEnvironment.TESTNET) but run the NT
engine as a fake node, so they need the nautilus extra (importorskip); the
NoopHost cells run on a base install.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custos.core.deployment_reconciler import DeploymentReconciler
from custos.engines.nautilus import host as nautilus_host
from custos.engines.nautilus.host import NoopHost, NtTradingNodeHost
from custos.engines.nautilus.strategy_loader import compute_strategy_dir_hash


class _FakeTrader:
    def add_strategy(self, strategy) -> None:
        pass


class _FakeNode:
    """Minimal stand-in for TradingNode: records nothing, runs no engine. The
    host builds real venue configs into it; only the engine loop is faked."""

    def __init__(self, config) -> None:
        self.config = config
        self.trader = _FakeTrader()
        self._stop = asyncio.Event()

    def add_data_client_factory(self, name, factory) -> None:
        pass

    def add_exec_client_factory(self, name, factory) -> None:
        pass

    def build(self) -> None:
        pass

    async def run_async(self) -> None:
        await self._stop.wait()

    async def stop_async(self) -> None:
        self._stop.set()

    def dispose(self) -> None:
        pass


@pytest.fixture
def strategy_dir(tmp_path):
    d = tmp_path / "matrix"
    d.mkdir()
    (d / "strategy.py").write_text("class MatrixStrategy:\n    pass\n")
    return d


def _matrix_spec(mode: str, strategy_dir) -> dict:
    return {
        "spec_id": f"{mode}-1",
        "generation": 1,
        "trading_mode": mode,
        "lifecycle_state": "running",
        "connector": "binance_perpetual",
        "pairs": ["BTC-USDT"],
        "leverage": 1,
        "strategy_path": str(strategy_dir / "strategy.py"),
        "code_hash": compute_strategy_dir_hash(strategy_dir),
        "sandbox": {"starting_balances": ["10_000 USDT"]},
        "provenance_ref": {"credential_id": "cred-matrix"},
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
        execution_engine=host,
        credential_vault=vault,
    )
    return reconciler, nats_client


@pytest.mark.parametrize(
    ("mode", "host_kind"),
    [
        pytest.param("sandbox", "NoopHost", id="sandbox-NoopHost"),
        pytest.param("sandbox", "NtTradingNodeHost", id="sandbox-NtTradingNodeHost"),
        pytest.param("testnet", "NoopHost", id="testnet-NoopHost"),
        pytest.param("testnet", "NtTradingNodeHost", id="testnet-NtTradingNodeHost"),
    ],
)
async def test_mode_host_matrix(mode, host_kind, strategy_dir, monkeypatch) -> None:
    if host_kind == "NoopHost":
        host = NoopHost()
    else:
        pytest.importorskip("nautilus_trader")
        monkeypatch.setattr(nautilus_host, "TradingNode", _FakeNode)
        host = NtTradingNodeHost()

    reconciler, nats_client = _reconciler(host)
    spec = _matrix_spec(mode, strategy_dir)
    try:
        # Non-live → gate bypasses, deploy is admitted, status is running/healthy.
        await reconciler.handle_spec(spec)
        nats_client.publish_deployment_status.assert_awaited_once()
        payload = nats_client.publish_deployment_status.call_args.kwargs["payload"]
        assert payload["phase"] == "running"
        assert payload["health"] == "healthy"
    finally:
        await host.stop(spec["spec_id"])
