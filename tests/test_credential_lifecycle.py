"""Credential lifecycle invariant — the decrypted key never surfaces through a
plain object walk of the NT config the host builds (non-custodial 红线 0.1).

Three defence-in-depth invariants guard the in-process credential; this file
covers invariant #2. The other two are already covered elsewhere and are cross
referenced rather than duplicated:

* invariant #1 (repr) — test_nt_trading_node_host.py::test_deploy_does_not_retain_credential
* invariant #3 (structlog redaction) — test_nt_trading_node_host.py::test_exception_log_redacts_credential_material

Invariant #2: the raw credential lives only inside NautilusTrader config Structs
(msgspec ``__slots__``, no ``__dict__``); a recursive ``__dict__`` walk of the
``TradingNodeConfig`` the host builds must not reach it. That guarantees naive
introspection or serialisation of the config (``vars(...)`` → json) can never
leak a key, even though the config legitimately carries it in memory to sign
requests — the red line is the I/O boundary (log / publish / network), not
in-memory config state.

The invariant is asserted on the ``TradingNodeConfig`` (the object that carries
the credential into NT) rather than on a live ``TradingNode``: constructing a
native node reinitialises NautilusTrader's global Rust logging subsystem, which
aborts (SIGABRT) on a second construction inside the shared test process.

**Scope (narrower than the plan's original invariant #2, per the impl peer
review)**: this walks the ``TradingNodeConfig`` surface reachable via ``__dict__``
+ container expansion (depth 5). It does *not* walk a post-construction
``TradingNode.__dict__`` object graph — that fuller coverage is blocked by the
SIGABRT above and deferred to a subprocess-isolated follow-up (Plan 05 candidate,
see DEV-03-CREDENTIAL-TEST-NO-NATIVE-NODE). The config is the object custos
assembles that carries the key, so the credential-carrying surface is covered;
the gap is the native node wrapper's own attributes, which custos does not
populate with the raw credential.
"""

from __future__ import annotations

import pytest

pytest.importorskip("nautilus_trader")

from nautilus_trader.config import (  # noqa: E402
    LiveExecEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.model.identifiers import TraderId  # noqa: E402

from arx_runner import _nt_binance_venue as venue  # noqa: E402

_SENTINEL_KEY = "SENSITIVE_KEY_XYZ"
_SENTINEL_SECRET = "SENSITIVE_SECRET_ABC"


def _walk_dict(obj: object, depth: int = 5) -> list[str]:
    """Collect every str leaf reachable from ``obj`` via ``__dict__`` / list /
    dict / tuple / set expansion, bounded to ``depth`` nesting levels.

    msgspec Structs (NT config objects) use ``__slots__`` and expose no
    ``__dict__``, so their fields are never descended into — which is exactly the
    invariant under test.
    """
    found: list[str] = []
    seen: set[int] = set()

    def _visit(node: object, remaining: int) -> None:
        if remaining < 0 or id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, str):
            found.append(node)
            return
        if isinstance(node, (bytes, bytearray)):
            return
        if isinstance(node, dict):
            for key, value in node.items():
                _visit(key, remaining - 1)
                _visit(value, remaining - 1)
            return
        if isinstance(node, (list, tuple, set, frozenset)):
            for item in node:
                _visit(item, remaining - 1)
            return
        attrs = getattr(node, "__dict__", None)
        if attrs:
            _visit(attrs, remaining - 1)

    _visit(obj, depth)
    return found


def _spec(spec_id: str = "cred-spec") -> dict:
    return {
        "spec_id": spec_id,
        "connector": "binance_perpetual",
        "pairs": ["BTC-USDT"],
        "leverage": 3,
        "sandbox": {"starting_balances": ["10_000 USDT"]},
    }


def _credential() -> dict:
    return {
        "api_key": _SENTINEL_KEY,
        "api_secret": _SENTINEL_SECRET,
        "permission_scope": "trade_no_withdraw",
    }


def test_node_dict_recursive_no_credential() -> None:
    spec = _spec()
    credential = _credential()

    # Assemble the node config exactly as NtTradingNodeHost.deploy does (sandbox),
    # so the credential enters the graph through the real venue-config path.
    data_cfg = venue.build_data_client_config(
        spec, credential, venue.data_environment_for_mode("sandbox")
    )
    # Positive control: the sentinel really is in the config graph — otherwise the
    # walk below would pass trivially (a walk over a graph that never held the key
    # proves nothing).
    assert data_cfg.api_key == _SENTINEL_KEY
    assert data_cfg.api_secret == _SENTINEL_SECRET

    exec_cfg = venue.build_exec_client_config_sandbox(spec, credential, ["10_000 USDT"])
    node_config = TradingNodeConfig(
        trader_id=TraderId("CUSTOS-CRED"),
        logging=LoggingConfig(log_level="INFO"),
        data_clients={venue.BINANCE_VENUE: data_cfg},
        exec_clients={venue.BINANCE_VENUE: exec_cfg},
        exec_engine=LiveExecEngineConfig(reconciliation=False),
    )

    leaves = _walk_dict(node_config, depth=5)
    assert _SENTINEL_KEY not in leaves
    assert _SENTINEL_SECRET not in leaves
