"""Testnet paper-to-testnet end-to-end for the real SuperTrendStrategy.

**Testnet only** — this test is against the Binance USDT-M Futures testnet
endpoint using test-fund credentials. Feeding a mainnet API key into this test
would violate non-custodial red line 0.1 by exposing production credentials to
the offline test harness and to whatever CI environment runs it. The
``permission_scope`` guard in ``credential_vault`` (``trade_no_withdraw``
required for every deploy, mode-agnostic) is the second-line defence, but the
first line is operator discipline: only provision **testnet-issued** keys under
``$CUSTOS_TESTNET_VAULT_ROOT`` for this test.

The test is marked ``@pytest.mark.integration`` — it requires provisioned
infrastructure (a real testnet key in the local vault + reachability to
Binance's testnet endpoint) and does not participate in the deterministic
``make verify`` baseline. In a fresh environment with neither, the test
``pytest.skip`` s with a clear "not provisioned" reason and points the operator
at the manual verification path (DEV-08-T5.2-MANUAL-VERIFICATION in the plan's
deviation log): provision a testnet vault, run this test manually, capture
passing output as evidence.

Assertions on the golden path (all credentials provisioned + network reachable):

* Real routing: the exec-client config built for ``trading_mode="testnet"``
  targets ``BinanceEnvironment.TESTNET`` — a live-endpoint mis-route surfaces
  as an explicit failure rather than an accidental production deploy.
* Deploy round-trip: ``host.deploy(spec, credential)`` returns the spec_id
  container_id and registers a live TradingNode in the same shape the sandbox
  path uses (paper → testnet transition parity).
* Credential leak-negative: the sentinel-value discipline from the sandbox
  T5.1 test repeats here — the API key + secret loaded from the vault must not
  appear in stdout / stderr during the parked deploy path. Because the vault
  key is a real testnet secret (not a sentinel string), the assertion is
  keyed on the decrypted key value rather than a pre-known constant.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path

import pytest

pytest.importorskip("nautilus_trader")

from nautilus_trader.adapters.binance.common.enums import (  # noqa: E402
    BinanceAccountType,
    BinanceEnvironment,
)
from nautilus_trader.adapters.binance.config import BinanceExecClientConfig  # noqa: E402
from nautilus_trader.live.node import TradingNode  # noqa: E402

# Vendored toolkit sys.path bootstrap must precede any load of the fixture
# strategy — its ``from custos_toolkit.<pkg>`` imports are resolved at dynamic-load
# time.
from custos.engines.nautilus import venue_binance as venue  # noqa: E402
from custos.engines.nautilus.host import NtTradingNodeHost  # noqa: E402

_FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "real_supertrend"
_REAL_SUPERTREND = _FIXTURE_DIR / "strategy.py"
_REAL_SUPERTREND_CONFIG = _FIXTURE_DIR / "config.yaml"

# Env vars the operator sets to opt into the real testnet path. Kept together
# so the skip message can name them explicitly.
_ENV_ENABLE = "CUSTOS_T52_TESTNET_ENABLE"
_ENV_VAULT_ROOT = "CUSTOS_TESTNET_VAULT_ROOT"
_ENV_CREDENTIAL_ID = "CUSTOS_TESTNET_CREDENTIAL_ID"


@pytest.fixture(scope="module", autouse=True)
def _cleanup_supertrend_registry(clear_strategy_module_cache):
    """Drop the fixture registration and dynamic module cache at teardown.

    Same rationale as the sandbox test module's cleanup fixture: unregistering
    without evicting the deterministic loader cache leaves downstream tests
    with a cached module whose registration side effect cannot run again.
    """
    yield
    from custos_toolkit_nautilus.adapter import registry as ps_registry

    if ps_registry.is_registered("supertrend"):
        ps_registry.unregister_strategy("supertrend")
    clear_strategy_module_cache(_REAL_SUPERTREND)


def _load_strategy_config() -> dict:
    from custos_toolkit.config import load_yaml_file

    return load_yaml_file(_REAL_SUPERTREND_CONFIG)


def _spec(spec_id: str = "int-1") -> dict:
    return {
        "spec_id": spec_id,
        "strategy_path": str(_REAL_SUPERTREND),
        "strategy_registry_name": "supertrend",
        "strategy_config": _load_strategy_config(),
        "trading_mode": "testnet",
        "connector": "binance_perpetual",
        "pairs": ["BTC-USDT"],
        "leverage": 3,
    }


def _load_testnet_credential() -> dict:
    """Load the testnet credential from the operator-configured vault.

    Uses the same ``credential_vault`` decrypt path production uses, so the
    ``trade_no_withdraw`` scope-check runs. The ``CUSTOS_TESTNET_VAULT_ROOT``
    override tells the vault where to look on the operator's machine (avoids
    hardcoding a path that only works in one dev environment).
    """
    from custos.core.credential_vault import CredentialVault

    vault_root = os.environ.get(_ENV_VAULT_ROOT)
    credential_id = os.environ.get(_ENV_CREDENTIAL_ID)
    if not vault_root or not credential_id:
        raise RuntimeError(
            f"testnet vault env not fully set — {_ENV_VAULT_ROOT} and "
            f"{_ENV_CREDENTIAL_ID} required for real testnet run"
        )

    vault = CredentialVault(
        tenant_id="custos-t52-testnet",
        initiator="test-runner-08",
        vault_root=Path(vault_root),
    )
    return vault.decrypt(credential_id)


async def _parked_run(self) -> None:
    """Park run_async so the deploy path can be inspected without opening
    a live testnet session that would place actual orders.

    The plan calls for asserting real testnet routing + credential-safe
    telemetry emission; both are observable in the deploy window before
    ``run_async`` opens the session. Skipping the actual session keeps the
    test reproducible across operators without requiring an active testnet
    exchange handshake per run — which is the intent of the partial+manual
    verification fallback per DEV-08-T5.2-MANUAL-VERIFICATION.
    """
    await asyncio.get_running_loop().create_future()


async def _teardown(host: NtTradingNodeHost, spec_id: str) -> None:
    entry = host._active_nodes.pop(spec_id, None)
    if entry is None:
        return
    _node, task = entry
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def _skip_unless_provisioned() -> None:
    """Skip when the operator hasn't opted into the testnet infrastructure.

    Missing any of the three env vars means the test cannot run its real
    testnet exercise. The skip message names the manual verification path so
    the operator knows what to do next.
    """
    if os.environ.get(_ENV_ENABLE) != "1":
        pytest.skip(
            f"{_ENV_ENABLE} != 1 — testnet real-run is opt-in per DP1 partial+manual "
            "fallback. Set the env var, provision a testnet vault, and re-run this test "
            "manually per DEV-08-T5.2-MANUAL-VERIFICATION"
        )
    missing = [name for name in (_ENV_VAULT_ROOT, _ENV_CREDENTIAL_ID) if not os.environ.get(name)]
    if missing:
        pytest.skip(
            f"testnet vault env vars not set: {missing} — provision the local vault "
            "and re-run per DEV-08-T5.2-MANUAL-VERIFICATION"
        )


@pytest.mark.integration
def test_real_supertrend_testnet_routing_wire() -> None:
    """Wire-level assertion — no network, no vault.

    Even in the deferred / manual-verification default state, this cheap
    check guards against a red-line-0.2-adjacent boundary defect: if
    ``venue_binance.build_exec_client_config_testnet`` ever silently starts
    returning a live-endpoint config, the deploy path would route testnet
    intent to production. Assertable without a real credential (the config
    builder just reads spec + credential shape).
    """
    fake_spec = {
        "connector": "binance_perpetual",
        "pairs": ["BTC-USDT"],
        "leverage": 3,
    }
    fake_credential = {
        "api_key": "wire-check-not-a-real-key",
        "api_secret": "wire-check-not-a-real-secret",
        "permission_scope": "trade_no_withdraw",
    }

    exec_cfg = venue.build_exec_client_config_testnet(fake_spec, fake_credential)
    assert isinstance(exec_cfg, BinanceExecClientConfig), (
        "build_exec_client_config_testnet must return a BinanceExecClientConfig"
    )
    assert exec_cfg.environment is BinanceEnvironment.TESTNET, (
        f"exec_cfg.environment={exec_cfg.environment!r} is not TESTNET — the config "
        "builder routed testnet intent to a live/production endpoint (red-line-0.2 boundary)"
    )
    assert exec_cfg.account_type == BinanceAccountType.USDT_FUTURES, (
        f"exec_cfg.account_type={exec_cfg.account_type!r} does not match the "
        "USDT-M futures product family Plan 08 targets by default"
    )
    assert exec_cfg.us is False, (
        "exec_cfg.us=True mis-routes to Binance US; testnet exercise targets the "
        "global Binance testnet endpoint"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_supertrend_testnet_deploy(
    monkeypatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Real testnet e2e — provisions required. Skips otherwise.

    Golden path exercised only when the operator provisions the vault and
    opts in via the enable env var (partial+manual verification fallback).
    Assertions:

    * ``container_id == "int-1"`` — spec round-trip.
    * Registered class is the real ``SuperTrendStrategy`` (same as the
      sandbox test).
    * ``credential.api_key`` / ``api_secret`` (the real testnet secrets
      loaded from the vault) do not appear in captured stdout / stderr
      during the parked deploy path. Cross-mode discipline with T5.1: the
      real-strategy-path desensitisation must hold under testnet routing
      too, not just sandbox.

    The parked ``run_async`` means we do not open a live testnet session
    that would place orders; the OrderDenied / acknowledgement telemetry
    assertions the plan lists are the manual-verification-path responsibility
    (see DEV-08-T5.2-MANUAL-VERIFICATION), covered by an operator running
    the real-session variant off-band and capturing the output.
    """
    _skip_unless_provisioned()

    monkeypatch.setattr(TradingNode, "run_async", _parked_run, raising=True)

    credential = _load_testnet_credential()
    host = NtTradingNodeHost()
    try:
        container_id = await host.deploy(_spec(), credential)
        assert container_id == "int-1"

        node, task = host._active_nodes["int-1"]
        assert task is not None and not task.done()
        strategies = node.trader.strategies()
        assert len(strategies) == 1
        assert type(strategies[0]).__name__ == "SuperTrendStrategy"

        # Credential leak-negative (same discipline as T5.1, keyed on the
        # real decrypted secret rather than a sentinel constant).
        captured = capfd.readouterr()
        combined = captured.out + captured.err
        assert credential["api_key"] not in combined, (
            "testnet api_key leaked through an observability sink — red line 0.1 breach"
        )
        assert credential["api_secret"] not in combined, (
            "testnet api_secret leaked through an observability sink — red line 0.1 breach"
        )
    finally:
        await _teardown(host, "int-1")
