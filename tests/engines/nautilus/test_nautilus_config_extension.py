"""Assert deploy plumbs nautilus_config timeouts into the real TradingNodeConfig.

ps ``runner.py._create_node_config`` reads timeout_connection / timeout_reconciliation /
timeout_portfolio / timeout_disconnection + reconciliation_lookback_mins from the
strategy config and passes them to ``TradingNodeConfig`` / ``LiveExecEngineConfig``.
custos ships the same knobs via ``spec["nautilus_config"]`` (a plain dict-key on the
DeploymentSpec; not a Pydantic field, per plan §DEV-06-DEPLOYMENTSPEC-DICT-NOT-CLASS).

The assertion is done by intercepting ``TradingNode.__init__`` and inspecting the
config it receives — this drives the real host-side plumb without needing to bring
up a full sandbox lifecycle.

Venue mismatch (G6 layer 2) is not asserted here — it already has dedicated
coverage in ``test_g6_gate_capability_e2e.py`` (asserts the
``g6_gate_venue_unsupported`` log event fires for live + unsupported venue).
Duplicating it here would only aim the same guard from a different angle without
adding independent value.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("nautilus_trader")

from nautilus_trader.live.node import TradingNode  # noqa: E402

from custos.engines.nautilus.host import NtTradingNodeHost  # noqa: E402

# tests/engines/nautilus/<this> -> tests/fixtures/minimal_supertrend_strategy.py
_FIXTURE_STRATEGY = Path(__file__).parents[2] / "fixtures" / "minimal_supertrend_strategy.py"


def _spec(**overrides: Any) -> dict:
    spec = {
        "spec_id": "cfg-1",
        "deployment_instance_id": "cfg-1",
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
    await asyncio.get_running_loop().create_future()


async def _teardown(host: NtTradingNodeHost, spec_id: str) -> None:
    """Cancel the parked run task and forget the node without invoking a real
    NT shutdown — matching the pattern in test_nt_trading_node_host_integration."""
    entry = host._active_nodes.pop(spec_id, None)
    if entry is None:
        return
    _, task = entry
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


class _ConfigCaptor:
    """Wrap TradingNode.__init__ so tests can inspect the assembled config
    without running a full lifecycle. Delegates back to the real __init__ so
    build() / add_*_client_factory still work. Each install() resets the
    per-test capture slot so class-level state can't bleed between tests."""

    captured: Any = None

    @classmethod
    def install(cls, monkeypatch: pytest.MonkeyPatch) -> None:
        cls.captured = None
        real_init = TradingNode.__init__

        def _capture(self, *, config, **kwargs):
            cls.captured = config
            real_init(self, config=config, **kwargs)

        monkeypatch.setattr(TradingNode, "__init__", _capture, raising=True)


@pytest.mark.asyncio
async def test_nautilus_config_timeouts_plumbed(monkeypatch: pytest.MonkeyPatch) -> None:
    """spec['nautilus_config'] timeout/reconciliation knobs reach TradingNodeConfig."""
    _ConfigCaptor.install(monkeypatch)
    monkeypatch.setattr(TradingNode, "run_async", _parked_run, raising=True)

    host = NtTradingNodeHost()
    spec = _spec(
        nautilus_config={
            "timeout_connection": 45.0,
            "timeout_reconciliation": 20.0,
            "timeout_portfolio": 15.0,
            "timeout_disconnection": 12.0,
            "reconciliation_lookback_mins": 720,
        },
    )
    try:
        await host.deploy(spec, _credential())
        cfg = _ConfigCaptor.captured
        assert cfg is not None, "TradingNodeConfig must have been assembled"
        assert cfg.timeout_connection == 45.0
        assert cfg.timeout_reconciliation == 20.0
        assert cfg.timeout_portfolio == 15.0
        assert cfg.timeout_disconnection == 12.0
        assert cfg.exec_engine.reconciliation_lookback_mins == 720
    finally:
        await _teardown(host, "cfg-1")


@pytest.mark.asyncio
async def test_nautilus_config_defaults_when_key_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """No nautilus_config key => NT internal defaults, existing behaviour preserved."""
    _ConfigCaptor.install(monkeypatch)
    monkeypatch.setattr(TradingNode, "run_async", _parked_run, raising=True)

    host = NtTradingNodeHost()
    try:
        await host.deploy(_spec(spec_id="cfg-def"), _credential())
        cfg = _ConfigCaptor.captured
        # NT internal defaults (per TradingNodeConfig field defaults).
        assert cfg.timeout_connection == 60.0
        assert cfg.timeout_reconciliation == 30.0
        assert cfg.timeout_portfolio == 10.0
        assert cfg.timeout_disconnection == 10.0
        # reconciliation_lookback_mins defaults to None on LiveExecEngineConfig.
        assert cfg.exec_engine.reconciliation_lookback_mins is None
    finally:
        await _teardown(host, "cfg-def")


@pytest.mark.asyncio
async def test_nautilus_config_partial_dict_uses_defaults_for_missing_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial nautilus_config dict overrides only the keys it sets; the rest
    fall back to NT internal defaults, so downstream operators can bump one knob
    without having to restate the whole block."""
    _ConfigCaptor.install(monkeypatch)
    monkeypatch.setattr(TradingNode, "run_async", _parked_run, raising=True)

    host = NtTradingNodeHost()
    spec = _spec(
        spec_id="cfg-partial",
        nautilus_config={"timeout_reconciliation": 25.0},
    )
    try:
        await host.deploy(spec, _credential())
        cfg = _ConfigCaptor.captured
        assert cfg.timeout_reconciliation == 25.0  # overridden
        assert cfg.timeout_connection == 60.0  # NT default
        assert cfg.timeout_portfolio == 10.0  # NT default
        assert cfg.exec_engine.reconciliation_lookback_mins is None  # NT default
    finally:
        await _teardown(host, "cfg-partial")
