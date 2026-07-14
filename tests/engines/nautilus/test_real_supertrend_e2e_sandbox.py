"""Sandbox end-to-end for the real SuperTrendStrategy via the vendored toolkit.

Reverses the deliberate avoidance in ``test_nt_trading_node_host_integration.py``
(which loads a self-contained ``MinimalSupertrendStrategy`` fixture to keep the
host lifecycle path free of runtime ``philosophers-stone/shared/`` coupling).
Here we load the real ``SuperTrendStrategy`` from a permanent in-repo mirror at
``tests/fixtures/real_supertrend/`` — its ``from custos_toolkit.<pkg>`` imports resolve
through the vendored toolkit substrate (``import custos.engines.nautilus.toolkit``
prepends ``toolkit/`` to ``sys.path``), so no sibling ps repo checkout is needed
at test time. Independent-clone reproducible by construction.

Two acceptances land here:

1. ``test_real_supertrend_loads_and_deploys_sandbox`` — golden path: the real
   ps strategy class survives the vendored-toolkit load path, the registry-name
   binding is intact, the deploy call registers a live ``TradingNode``, and the
   strategy config carries the production-tier risk-management values that Plan
   06 Track 2 (ps commit ``3443e96``) baked into ``config.yaml``. These config
   values are the runtime signal that ``RiskControlCoordinator.init_risk_controls``
   will install a non-``None`` ``_risk_controller`` when the strategy's ``on_start``
   runs (out of scope for a monkeypatched ``run_async`` in-process test — see the
   assertion notes for the config-layer proxy rationale).

2. ``test_credential_not_in_telemetry_payload_supertrend`` — non-custodial red
   line 0.1 real-strategy positive control: sentinel API key + secret values are
   fed into the deploy path, then all captured stdout / stderr from the parked
   deploy are searched for those sentinels. Absence is the required outcome; a
   hit means a future sink was added without hooking through the shared
   desensitisation path.

Both tests park ``TradingNode.run_async`` (no exchange connectivity in offline
CI) but let everything up to it — config assembly, node.build, factory-probe
instantiation, telemetry attach best-effort — run against genuine NT machinery.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import pytest

pytest.importorskip("nautilus_trader")

from nautilus_trader.live.node import TradingNode  # noqa: E402

# Bootstrap the vendored toolkit's sys.path before importing the loader — the
# ``custos_toolkit.*`` imports in the fixture strategy are resolved during dynamic load,
# and the loader itself lazy-imports ``custos_toolkit_nautilus.adapter.registry`` when the
# registry-name check runs. Ordering here is load-bearing.
from custos.engines.nautilus.host import NtTradingNodeHost  # noqa: E402

_FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "real_supertrend"
_REAL_SUPERTREND = _FIXTURE_DIR / "strategy.py"
_REAL_SUPERTREND_CONFIG = _FIXTURE_DIR / "config.yaml"

# Sentinel credential values — chosen to be impossible in any real API key
# format so a partial-substring match would still fire.
_SENTINEL_API_KEY = "SENTINEL-KEY-DO-NOT-LEAK-A1B2C3-CUSTOS-08-T5-1"
_SENTINEL_API_SECRET = "SENTINEL-SECRET-DO-NOT-LEAK-X9Y8Z7-CUSTOS-08-T5-1"


@pytest.fixture(scope="module", autouse=True)
def _cleanup_supertrend_registry():
    """Drop the fixture-owned 'supertrend' registration at module teardown.

    Loading ``tests/fixtures/real_supertrend/strategy.py`` fires its
    module-level ``register_strategy("supertrend", ...)`` and binds the
    fixture's ``SuperTrendStrategy`` class into the shared ps registry. Left
    in place, that entry blocks any downstream test module (e.g.
    ``test_strategy_loader_registry_mode.py``) that loads the sibling ps repo's
    ``SuperTrendStrategy`` — the registry is idempotent only when the same
    class object re-registers, and the ps class object is not identity-equal to
    the fixture's cached copy.

    Both tests in this module can share one registration during the module's
    run (the fixture module is ``sys.modules``-cached; a second
    ``load_strategy_class`` call returns the cached module without re-running
    the top-level ``register_strategy`` call). Cleanup fires exactly once at
    module teardown, restoring an empty registry slot for downstream test
    modules.
    """
    yield
    from custos_toolkit_nautilus.adapter import registry as ps_registry

    if ps_registry.is_registered("supertrend"):
        ps_registry.unregister_strategy("supertrend")


def _load_strategy_config() -> dict:
    """Load the pinned SuperTrend config.yaml via the vendored toolkit loader.

    Uses ``custos_toolkit.config.load_yaml_file`` (resolved through the toolkit sys.path
    bootstrap at module top) so the fixture goes through the same YAML loading
    path production uses; keeps the fixture parity honest.
    """
    from custos_toolkit.config import load_yaml_file

    return load_yaml_file(_REAL_SUPERTREND_CONFIG)


def _spec(spec_id: str = "int-1", **overrides) -> dict:
    """Build a sandbox DeploymentSpec pointing at the real-supertrend fixture.

    ``code_hash`` deliberately omitted so ``load_strategy_class`` exercises its
    sandbox skip path (no dir-hash gate for the fixture; the gate is asserted
    against directory-level integrity, which is not what this sandbox test
    verifies). ``strategy_registry_name="supertrend"`` turns on the loader's
    post-load registry binding check.
    """
    spec = {
        "spec_id": spec_id,
        "deployment_instance_id": spec_id,
        "strategy_path": str(_REAL_SUPERTREND),
        "strategy_registry_name": "supertrend",
        "strategy_config": _load_strategy_config(),
        "connector": "binance_perpetual",
        "pairs": ["BTC-USDT"],
        "leverage": 3,
        "sandbox": {"starting_balances": ["10_000 USDT"]},
    }
    spec.update(overrides)
    return spec


def _credential(**overrides) -> dict:
    cred = {
        "api_key": _SENTINEL_API_KEY,
        "api_secret": _SENTINEL_API_SECRET,
        "permission_scope": "trade_no_withdraw",
    }
    cred.update(overrides)
    return cred


async def _parked_run(self) -> None:
    """Stand in for TradingNode.run_async: park until cancelled.

    Real ``run_async`` connects to Binance; offline CI has no exchange link. The
    parked task must be awaited exactly once (build + add_strategy + task
    creation all fire) so the assertions below observe the post-deploy state.
    """
    await asyncio.get_running_loop().create_future()


async def _teardown(host: NtTradingNodeHost, spec_id: str) -> None:
    """Cancel the parked run task and drop the spec from the active registry.

    Mirrors the deterministic teardown pattern from
    ``test_full_lifecycle_sandbox_supertrend``: pop first so any stale
    done-callback sees the entry gone, then cancel + suppress the expected
    ``CancelledError``.
    """
    entry = host._active_nodes.pop(spec_id, None)
    if entry is None:
        return
    _node, task = entry
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_real_supertrend_loads_and_deploys_sandbox(monkeypatch) -> None:
    """Golden path — real ``SuperTrendStrategy`` deploys through the vendored toolkit.

    Assertions in order:

    * ``container_id == "int-1"`` — spec_id round-trip.
    * ``host._active_nodes["int-1"]`` is a live (node, task) entry.
    * ``type(strategy).__name__ == "SuperTrendStrategy"`` — the real ps class,
      not the ``MinimalSupertrendStrategy`` fixture. If this ever regresses,
      the vendored-toolkit factory-probe integration has broken.
    * Registry binding: ``ps_registry.get_strategy_info("supertrend")["strategy_class"]``
      is the loaded class. This is the post-load introspection surface from
      Plan 06 Track 1 (``strategy_registry_name`` acceptance).
    * ``strategy.config.risk.global_risk.{max_daily_loss, max_drawdown,
      consecutive_loss_pause}`` carry the production-tier values Plan 06 Track
      2 baked into the ps ``config.yaml`` (``0.05 / 0.15 / 5``). This is a
      config-layer proxy for RiskController activation — the actual
      ``_risk_controller`` attribute is instantiated inside
      ``RiskControlCoordinator.init_risk_controls``, which fires from the
      strategy's ``on_start`` hook. ``on_start`` requires a running NT event
      loop (subscriptions, orderbook, warmup) that a monkeypatched
      ``run_async`` deliberately parks; instantiation-time
      ``_risk_controller`` is always ``None`` (see
      ``toolkit/shared/nautilus/trading_strategy.py`` initialiser). Config-layer
      values are the truthful gate this test can assert. Runtime activation is
      covered end-to-end by the ps-side test
      ``test_supertrend_risk_controller_enabled.py`` (Plan 06 Track 2).
    """
    monkeypatch.setattr(TradingNode, "run_async", _parked_run, raising=True)

    host = NtTradingNodeHost()
    try:
        container_id = await host.deploy(_spec(), _credential())
        assert container_id == "int-1"
        assert "int-1" in host._active_nodes

        node, task = host._active_nodes["int-1"]
        assert node is not None, "TradingNode registration failed"
        assert task is not None and not task.done(), "background run task should be parked"

        strategies = node.trader.strategies()
        assert len(strategies) == 1, (
            f"expected exactly one registered strategy, got {len(strategies)}"
        )
        strategy = strategies[0]

        assert type(strategy).__name__ == "SuperTrendStrategy", (
            f"expected real ps SuperTrendStrategy, got {type(strategy).__name__} — "
            "vendored-toolkit factory-probe integration has regressed"
        )

        # Registry-binding introspection: the loader accepted
        # strategy_registry_name="supertrend" (no ValueError raised), and the
        # registry maps that name back to the exact class the deploy loaded.
        from custos_toolkit_nautilus.adapter import registry as ps_registry

        info = ps_registry.get_strategy_info("supertrend")
        assert info["strategy_class"] is type(strategy), (
            "ps registry binds 'supertrend' to a class other than the one "
            "the loader picked — post-load introspection is broken"
        )

        # Config-layer proxy for RiskController activation (see docstring).
        global_risk = strategy.config.risk.global_risk
        assert global_risk.max_daily_loss == pytest.approx(0.05), (
            f"supertrend config.max_daily_loss={global_risk.max_daily_loss} "
            "does not match Plan 06 Track 2 production-tier value 0.05"
        )
        assert global_risk.max_drawdown == pytest.approx(0.15), (
            f"supertrend config.max_drawdown={global_risk.max_drawdown} "
            "does not match Plan 06 Track 2 production-tier value 0.15"
        )
        assert global_risk.consecutive_loss_pause == 5, (
            f"supertrend config.consecutive_loss_pause={global_risk.consecutive_loss_pause} "
            "does not match Plan 06 Track 2 production-tier value 5"
        )
    finally:
        await _teardown(host, "int-1")


@pytest.mark.asyncio
async def test_credential_not_in_telemetry_payload_supertrend(
    monkeypatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Non-custodial red line 0.1 — sentinel credential must NOT appear in any
    observable output during a real-supertrend sandbox deploy.

    Adds a real-strategy-path anchor to the existing desensitisation
    invariants: repr-safety and structlog redaction are already covered against
    the fake node in ``test_nt_trading_node_host.py``, and the recursive
    ``__dict__`` walk of ``TradingNodeConfig`` is covered in
    ``test_credential_lifecycle.py``. This test closes the third invariant on
    the real-strategy sandbox path: any sink emitting during a live deploy
    (``code_hash_skipped_sandbox``, ``nt_deploy_started``,
    ``nt_observability_attached``, or a future sink added without hooking
    through the shared processor) must not leak the sentinel.

    ``capfd`` captures at the file-descriptor level, which is what structlog's
    ``PrintLoggerFactory`` writes through — plain ``caplog`` (stdlib logging
    only) would miss it.
    """
    monkeypatch.setattr(TradingNode, "run_async", _parked_run, raising=True)

    host = NtTradingNodeHost()
    try:
        container_id = await host.deploy(_spec(), _credential())
        assert container_id == "int-1"

        # Read whatever has been emitted up to now — any pending structlog
        # events during deploy have already been printed.
        captured = capfd.readouterr()
        combined = captured.out + captured.err

        assert _SENTINEL_API_KEY not in combined, (
            "api_key sentinel leaked through an observability sink — "
            "non-custodial red line 0.1 breach; a new sink was added without "
            "hooking through the shared desensitisation processor"
        )
        assert _SENTINEL_API_SECRET not in combined, (
            "api_secret sentinel leaked through an observability sink — "
            "non-custodial red line 0.1 breach"
        )
    finally:
        await _teardown(host, "int-1")
