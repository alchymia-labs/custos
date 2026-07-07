"""Integration — a real NautilusTrader TradingNode driven end-to-end by the host.

Unlike test_nt_trading_node_host.py (fake node, unit-level control flow), this
builds a *real* NT TradingNode with the real Binance sandbox venue configs and
loads a self-contained, SuperTrend-shaped minimal ``nautilus_trader.trading``
``Strategy`` subclass fixture; there is no runtime dependency on
``philosophers-stone/shared/`` (the real supertrend couples to that package,
which custos must not reach into). Only the network I/O (run_async) is stubbed,
since CI has no exchange connectivity — everything else (config assembly,
node.build(), SimulatedExchange wiring, strategy registration) is the genuine
NautilusTrader machinery.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import pytest

pytest.importorskip("nautilus_trader")

from nautilus_trader.live.node import TradingNode  # noqa: E402

from arx_runner import nautilus_host  # noqa: E402
from arx_runner._strategy_loader import CodeHashMismatch  # noqa: E402
from arx_runner.nautilus_host import NtTradingNodeHost  # noqa: E402

_FIXTURE_STRATEGY = Path(__file__).parent / "fixtures" / "minimal_supertrend_strategy.py"


def _spec(spec_id: str = "int-1", **overrides) -> dict:
    spec = {
        "spec_id": spec_id,
        "strategy_path": str(_FIXTURE_STRATEGY),
        "connector": "binance_perpetual",
        "pairs": ["BTC-USDT"],
        "leverage": 3,
        "sandbox": {"starting_balances": ["10_000 USDT"]},
    }
    spec.update(overrides)
    return spec


def _credential() -> dict:
    return {
        "api_key": "test-key",
        "api_secret": "test-secret",
        "permission_scope": "trade_no_withdraw",
    }


async def _parked_run(self) -> None:
    # Stand in for run_async: park until cancelled (no exchange connection in CI).
    await asyncio.get_running_loop().create_future()


@pytest.mark.asyncio
async def test_full_lifecycle_sandbox_supertrend(monkeypatch) -> None:
    """Drive a real NT TradingNode through the sandbox deploy lifecycle.

    Uses a self-contained, SuperTrend-shaped minimal
    ``nautilus_trader.trading.Strategy`` subclass fixture; no runtime dependency
    on ``philosophers-stone/shared/``. run_async is parked (real run_async
    connects to Binance — out of scope for offline CI). Everything up to it is
    the genuine NT machinery: real venue configs → TradingNode → build() →
    SimulatedExchange → strategy registration. host.stop()'s graceful
    stop_async/dispose path is unit-tested against the fake node (NT's dispose
    stops the loop it doesn't own here).
    """
    monkeypatch.setattr(TradingNode, "run_async", _parked_run, raising=True)

    host = NtTradingNodeHost()
    container_id = await host.deploy(_spec(), _credential())
    assert container_id == "int-1"

    node, task = host._active_nodes["int-1"]
    strategies = node.trader.strategies()
    assert len(strategies) == 1
    assert type(strategies[0]).__name__ == "MinimalSupertrendStrategy"

    # Tear down the parked run task deterministically.
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    host._active_nodes.pop("int-1", None)


@pytest.mark.asyncio
async def test_deploy_missing_nt_extra_fails_fast(monkeypatch) -> None:
    monkeypatch.setattr(nautilus_host, "TradingNode", None)
    host = NtTradingNodeHost()
    with pytest.raises(RuntimeError, match="nt-runtime"):
        await host.deploy(_spec(), _credential())


@pytest.mark.asyncio
async def test_deploy_code_hash_mismatch_rejected() -> None:
    # Tampered code_hash must be rejected before any NT node is built.
    host = NtTradingNodeHost()
    with pytest.raises(CodeHashMismatch):
        await host.deploy(_spec(code_hash="deadbeef" * 8), _credential())
