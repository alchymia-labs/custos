"""NT 进程监管 + ExecutionEngineAdapter 的 CEX/NT 实现（设计 for 3、实现 1）。

Two hosts satisfy NautilusHostProtocol (deployment_reconciler.py):
- NoopHost: stub for paper / dev / sim — the G6 gate rejects it on live.
- NtTradingNodeHost: real NautilusTrader host. deploy dispatches on
  spec.trading_mode: sandbox (real-time data + locally simulated execution),
  testnet (real Binance exec on the testnet endpoint), and live (real exchange,
  gated by the G6 host gate + separation-of-duties approval).

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
from arx_runner.nats_client import ArxNatsClient
from arx_runner.nt_risk_engine import NtRiskEngineBridge
from arx_runner.telemetry_actor import (
    DEFAULT_TELEMETRY_EVENT_TYPES,
    ArxNatsTelemetryAdapter,
    NtTelemetryBridge,
    TelemetryActor,
    TelemetryActorConfig,
)

try:
    from nautilus_trader.adapters.binance.factories import (
        BinanceLiveDataClientFactory,
        BinanceLiveExecClientFactory,
    )
    from nautilus_trader.adapters.sandbox.factory import SandboxLiveExecClientFactory
    from nautilus_trader.config import LiveExecEngineConfig, LoggingConfig, TradingNodeConfig
    from nautilus_trader.live.node import TradingNode
    from nautilus_trader.model.identifiers import TraderId
except ImportError:  # nt-runtime extra absent (audit / paper install) — deploy fails fast
    BinanceLiveDataClientFactory = None
    BinanceLiveExecClientFactory = None
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

# Venues NtTradingNodeHost can execute. Declared NT-free here so the G6 gate can
# query capability on a base install, and kept in sync with the venue-config
# module's wired connectors by a drift-guard test (test_nt_binance_venue.py).
_SUPPORTED_VENUES = frozenset({"binance", "binance_perpetual"})

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
    使 reconciler 可 ducktype 依赖，G6 gate 查 supports_live 立即拒绝。
    """

    async def deploy(self, spec: dict, credential: dict) -> str:
        spec_id = spec.get("spec_id")
        _log.info("nautilus_host_deploy_stub", spec_id=spec_id)
        return f"container-{spec_id}"

    async def reconfigure(self, spec: dict) -> None:
        _log.info("nautilus_host_reconfigure_stub", spec_id=spec.get("spec_id"))

    async def stop(self, spec_id: str) -> None:
        _log.info("nautilus_host_stop_stub", spec_id=spec_id)

    def supports_live(self) -> bool:
        # Fail-safe: a stub that neither routes orders nor holds venue state must
        # never claim live capability — the G6 gate rejects it on live.
        return False

    def supports_venue(self, venue: str) -> bool:
        return False


class NtTradingNodeHost:
    """Real NautilusTrader host for Binance sandbox / testnet / live deployments.

    deploy assembles a TradingNode (Binance data + an execution client chosen by
    spec.trading_mode) and runs it in a background asyncio task so the reconcile
    loop is never blocked. stop tears the node down gracefully with a bounded
    timeout.

    non-custodial 红线 0.1: the decrypted credential is used only to build the
    NT data-client config and is never stored on the host, logged, or published.

    Observability (telemetry + pre-trade reject bridges) is opt-in: pass a NATS
    client + identity to wire it. Without one (G6 capability probes, unit tests)
    deploy runs the trade path only and never touches the MessageBus.
    """

    def __init__(
        self,
        *,
        telemetry_client: ArxNatsClient | None = None,
        tenant_id: str | None = None,
        runner_id: str | None = None,
    ) -> None:
        # spec_id -> (TradingNode, background run task). Never holds credentials.
        self._active_nodes: dict[str, tuple] = {}
        # spec_id -> live TelemetryActor, so stop() drains + cancels its loops.
        self._telemetry_actors: dict[str, TelemetryActor] = {}
        # Strong refs to fire-and-forget actor-teardown tasks scheduled from the
        # sync done-callback, so the loop doesn't GC them mid-shutdown.
        self._cleanup_tasks: set = set()
        self._stop_timeout_secs = _STOP_TIMEOUT_SECS
        self._telemetry_client = telemetry_client
        self._tenant_id = tenant_id
        self._runner_id = runner_id

    @staticmethod
    def _ensure_nt_available() -> None:
        if TradingNode is None:
            raise RuntimeError(
                "NautilusTrader not installed — install `custos-runner[nt-runtime]` "
                "(needs Python 3.12+) to run NtTradingNodeHost"
            )

    def supports_live(self) -> bool:
        return True

    def supports_venue(self, venue: str) -> bool:
        return venue.lower() in _SUPPORTED_VENUES

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

        trading_mode = str(spec.get("trading_mode") or "sandbox").lower()
        data_cfg = venue.build_data_client_config(
            spec, credential, venue.data_environment_for_mode(trading_mode)
        )
        exec_cfg, exec_factory, reconciliation = self._build_exec_plan(
            trading_mode, spec, credential, venue
        )

        node_config = TradingNodeConfig(
            trader_id=TraderId(self._trader_id(spec_id)),
            logging=LoggingConfig(log_level=str(spec.get("log_level", "INFO"))),
            data_clients={venue.BINANCE_VENUE: data_cfg},
            exec_clients={venue.BINANCE_VENUE: exec_cfg},
            # Real venues reconcile against exchange account state; the sandbox has none.
            exec_engine=LiveExecEngineConfig(reconciliation=reconciliation),
        )

        try:
            node = TradingNode(config=node_config)
            node.add_data_client_factory(venue.BINANCE_VENUE, BinanceLiveDataClientFactory)
            node.add_exec_client_factory(venue.BINANCE_VENUE, exec_factory)
            node.build()
        except Exception as exc:  # noqa: BLE001 — reconciler maps this to degraded status
            _log.error("nt_startup_failure", spec_id=spec_id, **_sanitize_exception(exc))
            raise

        # Attach observability once the MessageBus exists (post-build), before
        # the strategy starts emitting events. Best-effort — see docstring.
        await self._attach_observability(node, spec_id)

        node.trader.add_strategy(strategy)

        task = asyncio.create_task(node.run_async())
        task.add_done_callback(lambda t, sid=spec_id: self._on_node_task_done(sid, t))
        self._active_nodes[spec_id] = (node, task)

        _log.info(
            "nt_deploy_started",
            spec_id=spec_id,
            trading_mode=trading_mode,
            connector=spec.get("connector"),
            permission_scope=credential.get("permission_scope"),
            strategy=type(strategy).__name__,
        )
        return spec_id

    def _build_exec_plan(self, trading_mode: str, spec: dict, credential: dict, venue):
        """Resolve (exec_config, exec_factory, reconciliation) for the trading mode.

        sandbox fills locally against live prices (no exchange contact); testnet /
        live place real orders on the Binance testnet / live endpoints. Real venues
        reconcile against exchange account state, the sandbox has none. A live plan
        emits an operational warning and cannot be built without dual approval
        (enforced inside build_exec_client_config_live).
        """
        if trading_mode == "sandbox":
            starting_balances = (spec.get("sandbox") or {}).get(
                "starting_balances"
            ) or _DEFAULT_STARTING_BALANCES
            exec_cfg = venue.build_exec_client_config_sandbox(spec, credential, starting_balances)
            return exec_cfg, SandboxLiveExecClientFactory, False
        if trading_mode == "testnet":
            exec_cfg = venue.build_exec_client_config_testnet(spec, credential)
            return exec_cfg, BinanceLiveExecClientFactory, True
        if trading_mode == "live":
            _log.warning(
                "nt_live_deploy_requested",
                spec_id=spec.get("spec_id"),
                connector=spec.get("connector"),
                approver_count=len({a for a in (spec.get("approved_by") or []) if a}),
            )
            exec_cfg = venue.build_exec_client_config_live(spec, credential)
            return exec_cfg, BinanceLiveExecClientFactory, True
        raise RuntimeError(
            f"unsupported trading_mode {trading_mode!r} (expected sandbox / testnet / live)"
        )

    async def _attach_observability(self, node, spec_id: str) -> None:
        """Attach the telemetry + pre-trade-reject bridges to a built node's
        MessageBus and start the telemetry actor.

        Best-effort: an attach failure degrades to observability loss (logged as
        ``telemetry_actor_attach_failed``), never aborts the deploy — the trade
        path is primary and losing the uplink must not stop trading (红线 0.3).
        No-op when the host was constructed without a telemetry client (G6
        capability probes / unit tests).
        """
        if self._telemetry_client is None:
            return
        actor = TelemetryActor(
            publisher=ArxNatsTelemetryAdapter(self._telemetry_client),
            tenant_id=self._tenant_id or "",
            runner_id=self._runner_id or "",
            config=TelemetryActorConfig(allowed_event_types=DEFAULT_TELEMETRY_EVENT_TYPES),
        )
        try:
            msgbus = node.kernel.msgbus
            # Start before subscribing so the actor loop owns the loop reference
            # before the first event can arrive.
            await actor.start()
            NtTelemetryBridge(actor=actor).bootstrap(msgbus)
            NtRiskEngineBridge(
                client=self._telemetry_client,
                tenant_id=self._tenant_id or "",
                runner_id=self._runner_id or "",
            ).bootstrap(msgbus)
        except Exception as exc:  # noqa: BLE001 — 红线 0.3: observability loss must not abort deploy
            _log.error("telemetry_actor_attach_failed", spec_id=spec_id, **_sanitize_exception(exc))
            await self._safe_stop_actor(actor)
            return
        self._telemetry_actors[spec_id] = actor
        _log.info(
            "nt_observability_attached",
            spec_id=spec_id,
            telemetry_session_id=actor.session_id,
        )

    async def _safe_stop_actor(self, actor: TelemetryActor) -> None:
        try:
            await actor.stop()
        except Exception as exc:  # noqa: BLE001 — stop-time cleanup must not raise into caller
            _log.error("telemetry_actor_stop_failed", error=str(exc))

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
        # Drain + cancel the telemetry actor after the engine has stopped so any
        # final buffered events still flush.
        actor = self._telemetry_actors.pop(spec_id, None)
        if actor is not None:
            await self._safe_stop_actor(actor)
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
            # Tear down the telemetry actor for a self-terminated node so its
            # flush / heartbeat loops don't linger (scheduled: we're on the loop).
            actor = self._telemetry_actors.pop(spec_id, None)
            if actor is not None:
                cleanup = asyncio.ensure_future(self._safe_stop_actor(actor))
                self._cleanup_tasks.add(cleanup)
                cleanup.add_done_callback(self._cleanup_tasks.discard)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            _log.error("nt_node_loop_failed", spec_id=spec_id, **_sanitize_exception(exc))
