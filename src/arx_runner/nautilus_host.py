"""NT 进程监管 + ExecutionEngineAdapter 的 CEX/NT 实现（设计 for 3、实现 1）。

Two hosts satisfy NautilusHostProtocol (deployment_reconciler.py):
- NoopHost: stub for paper / dev / sim — the G6 gate rejects it on live.
- NtTradingNodeHost: real NautilusTrader host. v1 covers Binance sandbox mode
  (real-time data + locally simulated execution); testnet / live is a later
  plan and stays blocked by the G6 gate until then.

NautilusTrader is an optional runtime (`nt-runtime` extra, Python 3.12+). This
module import-guards it so the reconciler can import NoopHost on a base install
without NT; NtTradingNodeHost.deploy fails fast if NT is missing.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from arx_runner._strategy_loader import load_strategy_class
from arx_runner.log import get_logger

try:
    from nautilus_trader.adapters.binance.factories import BinanceLiveDataClientFactory
    from nautilus_trader.adapters.sandbox.factory import SandboxLiveExecClientFactory
    from nautilus_trader.config import LiveExecEngineConfig, LoggingConfig, TradingNodeConfig
    from nautilus_trader.live.node import TradingNode
    from nautilus_trader.model.identifiers import TraderId
except ImportError:  # nt-runtime extra absent (audit / paper install) — deploy fails fast
    BinanceLiveDataClientFactory = None
    SandboxLiveExecClientFactory = None
    LiveExecEngineConfig = None
    LoggingConfig = None
    TradingNodeConfig = None
    TradingNode = None
    TraderId = None

__all__ = ["NoopHost", "NtTradingNodeHost"]

_log = get_logger("arx_runner.nautilus_host")

_DEFAULT_STARTING_BALANCES = ["10_000 USDT"]
_STOP_TIMEOUT_SECS = 30.0

# Substrings that flag an exception message as possibly carrying credential
# material (NT config repr, adapter auth errors) — such messages are redacted
# before logging so a raw key can never reach the log (non-custodial 红线 0.1).
_CREDENTIAL_HINTS = ("api_key", "api_secret", "secret", "authorization")


def _sanitize_exception(exc: Exception) -> dict:
    """Structured, credential-safe fields for logging an exception.

    If the message looks like it could embed credential material, drop it and
    keep only the exception type — a raw key must never be logged.
    """
    msg = str(exc)
    if any(hint in msg.lower() for hint in _CREDENTIAL_HINTS):
        return {
            "error_type": type(exc).__name__,
            "error": "<redacted: contained credential material>",
        }
    return {"error_type": type(exc).__name__, "error": msg}


class NoopHost:
    """Stub NautilusHost — 不真起 NT 进程，只记结构化日志后返回占位。

    仅供 paper / dev / sim mode 让 reconcile 流程跑通；live mode 由 G6 gate
    （deployment_reconciler._check_g6_gate）拒绝，因为 stub 会静默接受 live
    execution spec 却不实际执行。真实 NT host（NtTradingNodeHost）由后续
    adapter 落地后替换本 stub。

    方法签名与 NautilusHostProtocol（deployment_reconciler.py）逐字一致，
    使 reconciler 可 ducktype 依赖，G6 gate 可 isinstance 命中。
    """

    async def deploy(self, spec: dict, credential: dict) -> str:
        spec_id = spec.get("spec_id")
        _log.info("nautilus_host_deploy_stub", spec_id=spec_id)
        return f"container-{spec_id}"

    async def reconfigure(self, spec: dict) -> None:
        _log.info("nautilus_host_reconfigure_stub", spec_id=spec.get("spec_id"))

    async def stop(self, spec_id: str) -> None:
        _log.info("nautilus_host_stop_stub", spec_id=spec_id)


class NtTradingNodeHost:
    """Real NautilusTrader host for Binance sandbox deployments.

    deploy assembles a TradingNode (real-time Binance data + locally simulated
    execution) and runs it in a background asyncio task so the reconcile loop is
    never blocked. stop tears the node down gracefully with a bounded timeout.

    non-custodial 红线 0.1: the decrypted credential is used only to build the
    NT data-client config and is never stored on the host, logged, or published.
    """

    def __init__(self) -> None:
        # spec_id -> (TradingNode, background run task). Never holds credentials.
        self._active_nodes: dict[str, tuple] = {}
        self._stop_timeout_secs = _STOP_TIMEOUT_SECS

    @staticmethod
    def _ensure_nt_available() -> None:
        if TradingNode is None:
            raise RuntimeError(
                "NautilusTrader not installed — install `custos-runner[nt-runtime]` "
                "(needs Python 3.12+) to run NtTradingNodeHost"
            )

    async def deploy(self, spec: dict, credential: dict) -> str:
        self._ensure_nt_available()
        spec_id = spec["spec_id"]
        if spec_id in self._active_nodes:
            # Idempotency guard: re-deploying a live spec must go through stop first
            # (structural changes are stop + re-deploy), never silently replace it.
            raise RuntimeError(f"spec {spec_id!r} already deployed; call stop first")

        # Red line layer 1: verify code_hash before any strategy code is imported.
        strategy_path = Path(spec["strategy_path"])
        strategy_cls = load_strategy_class(strategy_path, spec.get("code_hash"))
        # Instantiate before building the node so a strategy-config failure never
        # leaves a built-but-unregistered node leaked.
        strategy = self._instantiate_strategy(strategy_cls, spec)

        # Imported lazily: _nt_binance_venue imports NautilusTrader at module top.
        from arx_runner import _nt_binance_venue as venue

        data_cfg = venue.build_data_client_config(spec, credential)
        starting_balances = (spec.get("sandbox") or {}).get(
            "starting_balances"
        ) or _DEFAULT_STARTING_BALANCES
        exec_cfg = venue.build_exec_client_config_sandbox(spec, credential, starting_balances)

        node_config = TradingNodeConfig(
            trader_id=TraderId(self._trader_id(spec_id)),
            logging=LoggingConfig(log_level=str(spec.get("log_level", "INFO"))),
            data_clients={venue.BINANCE_VENUE: data_cfg},
            exec_clients={venue.BINANCE_VENUE: exec_cfg},
            # Sandbox venue has no prior account state to reconcile against.
            exec_engine=LiveExecEngineConfig(reconciliation=False),
        )

        try:
            node = TradingNode(config=node_config)
            node.add_data_client_factory(venue.BINANCE_VENUE, BinanceLiveDataClientFactory)
            node.add_exec_client_factory(venue.BINANCE_VENUE, SandboxLiveExecClientFactory)
            node.build()
        except Exception as exc:  # noqa: BLE001 — reconciler maps this to degraded status
            _log.error("nt_startup_failure", spec_id=spec_id, **_sanitize_exception(exc))
            raise

        node.trader.add_strategy(strategy)

        task = asyncio.create_task(node.run_async())
        task.add_done_callback(lambda t, sid=spec_id: self._on_node_task_done(sid, t))
        self._active_nodes[spec_id] = (node, task)

        _log.info(
            "nt_deploy_started",
            spec_id=spec_id,
            connector=spec.get("connector"),
            permission_scope=credential.get("permission_scope"),
            strategy=type(strategy).__name__,
        )
        return spec_id

    async def stop(self, spec_id: str) -> None:
        entry = self._active_nodes.pop(spec_id, None)
        if entry is None:
            # Idempotent: stopping an unknown / already-stopped spec is a no-op.
            _log.info("nt_stop_noop_unknown_spec", spec_id=spec_id)
            return

        node, task = entry
        try:
            await asyncio.wait_for(node.stop_async(), timeout=self._stop_timeout_secs)
        except TimeoutError:
            _log.error("nt_stop_timeout", spec_id=spec_id, timeout_secs=self._stop_timeout_secs)
        finally:
            node.dispose()
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 — reaping the run task
                pass
        _log.info("nt_stop_completed", spec_id=spec_id)

    async def reconfigure(self, spec: dict) -> None:
        """v1 reconfigure: apply runtime-tunable params in place, reject structural.

        A running TradingNode cannot hot-swap its strategy class, venue, or traded
        symbols, so any structural change must go through stop + re-deploy (the
        reconciler owns the credential ref for that). Only changes the caller
        explicitly flags as runtime-tunable (leverage / notional cap) are accepted
        here; today they are logged as intent (live application is a follow-up).
        """
        spec_id = spec.get("spec_id")
        reconfigure_spec = spec.get("reconfigure") or {}
        if reconfigure_spec.get("runtime_tunable_only"):
            _log.info(
                "nt_reconfigure_runtime_tunable",
                spec_id=spec_id,
                params=reconfigure_spec.get("params"),
            )
            return
        raise NotImplementedError(
            f"structural reconfigure of spec {spec_id!r} requires spec drop + re-deploy "
            "(v1 NtTradingNodeHost does not hot-swap strategy / venue / symbol)"
        )

    def _instantiate_strategy(self, strategy_cls, spec: dict):
        """Instantiate the strategy: a module-level create_strategy(config) factory
        wins (ps-style entry point); otherwise the class with NT's default config.

        The module is resolved via sys.modules (the loader registers it there):
        inspect.getmodule returns None for dynamically-loaded strategy modules.
        """
        module = sys.modules.get(strategy_cls.__module__)
        factory = getattr(module, "create_strategy", None) if module is not None else None
        if callable(factory):
            return factory(spec.get("strategy_config", {}))
        return strategy_cls()

    @staticmethod
    def _trader_id(spec_id: str) -> str:
        tag = "".join(ch for ch in spec_id if ch.isalnum())[:20] or "000"
        return f"CUSTOS-{tag}"

    def _on_node_task_done(self, spec_id: str, task) -> None:
        # A background node loop dying must never be silent — surface the error.
        # Also drop the registry entry so a self-terminated node doesn't linger;
        # guard on task identity so a re-deployed spec_id (new task) isn't cleared
        # by a stale callback.
        entry = self._active_nodes.get(spec_id)
        if entry is not None and entry[1] is task:
            self._active_nodes.pop(spec_id, None)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            _log.error("nt_node_loop_failed", spec_id=spec_id, **_sanitize_exception(exc))
