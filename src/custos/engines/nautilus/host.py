"""NT process orchestration + ExecutionEngineAdapter CEX/NT implementation
(target: design for three, implement one).

Two hosts satisfy NautilusHostProtocol (deployment_reconciler.py):
- NoopHost: stub for paper / dev / sim — the G6 gate rejects it on live.
- NtTradingNodeHost: real NautilusTrader host. deploy dispatches on
  spec.trading_mode: sandbox (real-time data + locally simulated execution),
  testnet (real Binance exec on the testnet endpoint), and live (real exchange,
  gated by the G6 host gate + separation-of-duties approval).

NautilusTrader is an optional runtime (`nautilus` extra, Python 3.12+). This
module import-guards it so the reconciler can import NoopHost on a base install
without NT; NtTradingNodeHost.deploy fails fast if NT is missing.
"""

from __future__ import annotations

import asyncio
import sys
import time
from decimal import Decimal
from pathlib import Path

from custos.core.engine_protocol import (
    ConnectivityState,
    EngineStatus,
    OrderSnapshot,
    PositionSnapshot,
)
from custos.core.log import get_logger
from custos.core.runner_fact import (
    SUPPORTED_CURRENCIES,
    RunnerCapabilityReceipt,
    RunnerFactAuthority,
    RunnerFactEmitter,
)
from custos.core.runner_fact_producer import (
    RunnerFactDeployment,
    RunnerFactMessageBusBridge,
    VenueLedgerEvidence,
)
from custos.engines.nautilus.strategy_loader import load_strategy_class

try:
    from nautilus_trader.adapters.binance.factories import (
        BinanceLiveDataClientFactory,
        BinanceLiveExecClientFactory,
    )
    from nautilus_trader.adapters.sandbox.factory import SandboxLiveExecClientFactory
    from nautilus_trader.config import LiveExecEngineConfig, LoggingConfig, TradingNodeConfig
    from nautilus_trader.core.rust.model import PriceType
    from nautilus_trader.live.node import TradingNode
    from nautilus_trader.model.identifiers import TraderId
except ImportError:  # nautilus extra absent (audit / paper install) — deploy fails fast
    BinanceLiveDataClientFactory = None
    BinanceLiveExecClientFactory = None
    SandboxLiveExecClientFactory = None
    LiveExecEngineConfig = None
    LoggingConfig = None
    TradingNodeConfig = None
    TradingNode = None
    TraderId = None
    PriceType = None

__all__ = ["NoopHost", "NtTradingNodeHost"]

_log = get_logger("custos.nautilus_host")

_DEFAULT_STARTING_BALANCES = ["10_000 USDT"]
_STOP_TIMEOUT_SECS = 30.0

# Venues NtTradingNodeHost can execute. Declared NT-free here so the G6 gate can
# query capability on a base install, and kept in sync with the venue-config
# module's wired connectors by a drift-guard test (test_nt_binance_venue.py).
_SUPPORTED_VENUES = frozenset({"binance", "binance_perpetual"})

# Substrings that flag an exception message as potentially carrying credential
# material (NT config repr, adapter auth errors) — such messages are redacted
# before logging so a raw key can never reach the log (non-custodial red line 0.1).
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
    """Stub NautilusHost for non-execution path.

    It only logs structured events and returns placeholders so reconcile can run in
    paper / dev / sim mode. Live mode is rejected by the G6 gate
    (deployment_reconciler._check_g6_gate), because this stub would silently
    accept a live spec but never execute. A real NT host (NtTradingNodeHost) replaces
    this stub once the adapter is fully wired.

    The method signatures exactly match NautilusHostProtocol (deployment_reconciler.py)
    so reconciler can ducktype this dependency and G6 gate can immediately reject
    supports_live.
    """

    async def deploy(self, spec: dict, credential: dict) -> str:
        deployment_instance_id = str(spec.get("deployment_instance_id") or "")
        _log.info(
            "nautilus_host_deploy_stub",
            deployment_instance_id=deployment_instance_id,
        )
        return f"container-{deployment_instance_id}"

    async def reconfigure(self, spec: dict) -> None:
        _log.info(
            "nautilus_host_reconfigure_stub",
            deployment_instance_id=spec.get("deployment_instance_id"),
        )

    async def stop(self, deployment_instance_id: str) -> None:
        _log.info("nautilus_host_stop_stub", deployment_instance_id=deployment_instance_id)

    def supports_live(self) -> bool:
        # Fail-safe: a stub that neither routes orders nor holds venue state must
        # never claim live capability — the G6 gate rejects it on live.
        return False

    def supports_venue(self, venue: str) -> bool:
        return False

    async def get_open_notional(self, deployment_instance_id: str) -> Decimal:
        # Stub holds no positions — zero exposure. The runner cap / breaker are
        # correctly no-ops against it (NoopHost only ever runs paper / sim).
        return Decimal("0")

    async def check_engine_connected(self, deployment_instance_id: str) -> ConnectivityState:
        # Stub has no engine to disconnect — always reports connected so the
        # zombie watchdog never flags a paper/sim runner.
        return ConnectivityState(
            data_connected=True, exec_connected=True, checked_at_epoch_s=time.time()
        )

    async def flatten_positions(self, deployment_instance_id: str, reason: str) -> None:
        # Stub holds no positions — flatten is a no-op, logged so the breaker's
        # trip is still observable on a paper/sim runner.
        _log.info(
            "noophost_flatten_noop",
            deployment_instance_id=deployment_instance_id,
            reason=reason,
        )

    async def get_positions(self, deployment_instance_id: str) -> list[PositionSnapshot]:
        # Stub holds no positions — the snapshot publisher sees an empty list.
        return []

    async def get_orders(self, deployment_instance_id: str) -> list[OrderSnapshot]:
        return []

    async def get_engine_status(self, deployment_instance_id: str) -> EngineStatus:
        # Stub is always healthy with zero exposure; every money field is a
        # Decimal so the money-invariant guard on EngineStatus stays green.
        return EngineStatus(
            phase="running",
            position_count=0,
            order_count=0,
            open_notional=Decimal("0"),
            peak_equity=Decimal("0"),
            current_equity=Decimal("0"),
            drawdown_pct=Decimal("0"),
        )


class NtTradingNodeHost:
    """Real NautilusTrader host for Binance sandbox / testnet / live deployments.

    deploy assembles a TradingNode (Binance data + an execution client chosen by
    spec.trading_mode) and runs it in a background asyncio task so the reconcile
    loop is never blocked. stop tears the node down gracefully with a bounded
    timeout.

    non-custodial red line 0.1: the decrypted credential is used only to build the
    NT data-client config and is never stored on the host, logged, or published.

    Signed observations are opt-in: pass a RunnerFact emitter and capability
    receipt to wire the message-bus bridge. Deployment commands are the only
    NATS input; execution facts leave through the signed RunnerFact outbox.
    """

    def __init__(
        self,
        *,
        tenant_id: str | None = None,
        runner_id: str | None = None,
        runner_fact_emitter: RunnerFactEmitter | None = None,
        capability_receipt: RunnerCapabilityReceipt | None = None,
    ) -> None:
        # deployment_instance_id -> (TradingNode, background run task). Never holds credentials.
        self._active_nodes: dict[str, tuple] = {}
        # deployment_instance_id -> signed fact scope plus independent venue ledger adapter.
        self._runner_fact_contexts: dict[str, tuple[RunnerFactDeployment, object | None]] = {}
        # Decimal equity high-water mark per instance so get_engine_status can
        # report drawdown percentage over time. Never a float (red line 0.4).
        self._peak_equity: dict[str, Decimal] = {}
        self._stop_timeout_secs = _STOP_TIMEOUT_SECS
        self._tenant_id = tenant_id
        self._runner_id = runner_id
        self._runner_fact_emitter = runner_fact_emitter
        self._capability_receipt = capability_receipt

    @staticmethod
    def _ensure_nt_available() -> None:
        if TradingNode is None:
            raise RuntimeError(
                "NautilusTrader not installed — install `custos-runner[nautilus]` "
                "(needs Python 3.12+) to run NtTradingNodeHost"
            )

    def supports_live(self) -> bool:
        return True

    def supports_venue(self, venue: str) -> bool:
        return venue.lower() in _SUPPORTED_VENUES

    async def deploy(self, spec: dict, credential: dict) -> str:
        self._ensure_nt_available()
        spec_id = str(spec["spec_id"])
        deployment_instance_id = str(spec["deployment_instance_id"])
        if deployment_instance_id in self._active_nodes:
            # Idempotency guard: re-deploying a live spec must go through stop first
            # (structural changes are stop + re-deploy), never silently replace it.
            raise RuntimeError(
                f"deployment instance {deployment_instance_id!r} already deployed; call stop first"
            )

        # Red line layer 1: verify code_hash before any strategy code is imported.
        # strategy_registry_name (optional) turns on the second-line check that
        # the ps toolkit registry binds the operator-supplied name to the class
        # the loader picked — see load_strategy_class docstring.
        strategy_path = Path(spec["strategy_path"])
        strategy_cls = load_strategy_class(
            strategy_path,
            spec.get("code_hash"),
            expected_registry_name=spec.get("strategy_registry_name"),
        )
        # Instantiate before building the node so a strategy-config failure never
        # leaves a built-but-unregistered node leaked.
        strategy = self._instantiate_strategy(strategy_cls, spec)

        # Imported lazily: venue_binance imports NautilusTrader at module top.
        from custos.engines.nautilus import venue_binance as venue

        trading_mode = str(spec.get("trading_mode") or "sandbox").lower()
        data_cfg = venue.build_data_client_config(
            spec, credential, venue.data_environment_for_mode(trading_mode)
        )
        exec_cfg, exec_factory, reconciliation = self._build_exec_plan(
            trading_mode, spec, credential, venue
        )

        # ps runner.py._create_node_config exposes the NT startup timeouts and the
        # reconciliation lookback to strategy authors; custos accepts the same
        # knobs via a plain nautilus_config dict-key so operators can tune a slow
        # exchange without needing a code change. Every knob is optional — an
        # absent key falls through to the NT internal default.
        nautilus_cfg = spec.get("nautilus_config") or {}
        node_kwargs: dict = {
            "trader_id": TraderId(self._trader_id(deployment_instance_id)),
            "logging": LoggingConfig(log_level=str(spec.get("log_level", "INFO"))),
            "data_clients": {venue.BINANCE_VENUE: data_cfg},
            "exec_clients": {venue.BINANCE_VENUE: exec_cfg},
            # Real venues reconcile against exchange account state; the sandbox has none.
            "exec_engine": LiveExecEngineConfig(
                reconciliation=reconciliation,
                reconciliation_lookback_mins=nautilus_cfg.get("reconciliation_lookback_mins"),
            ),
        }
        for timeout_key in (
            "timeout_connection",
            "timeout_reconciliation",
            "timeout_portfolio",
            "timeout_disconnection",
        ):
            if timeout_key in nautilus_cfg:
                node_kwargs[timeout_key] = nautilus_cfg[timeout_key]

        node_config = TradingNodeConfig(**node_kwargs)

        try:
            node = TradingNode(config=node_config)
            node.add_data_client_factory(venue.BINANCE_VENUE, BinanceLiveDataClientFactory)
            node.add_exec_client_factory(venue.BINANCE_VENUE, exec_factory)
            node.build()
        except Exception as exc:  # noqa: BLE001 — reconciler maps this to degraded status
            _log.error(
                "nt_startup_failure",
                deployment_instance_id=deployment_instance_id,
                spec_id=spec_id,
                **_sanitize_exception(exc),
            )
            raise

        fact_context = self._build_runner_fact_context(spec, credential)
        try:
            self._attach_runtime_bridges(node, fact_context)
        except Exception:
            node.dispose()
            raise
        if fact_context is not None:
            self._runner_fact_contexts[fact_context[0].deployment_instance_id] = fact_context

        node.trader.add_strategy(strategy)

        task = asyncio.create_task(node.run_async())
        task.add_done_callback(
            lambda task, instance_id=deployment_instance_id: self._on_node_task_done(
                instance_id, task
            )
        )
        self._active_nodes[deployment_instance_id] = (node, task)

        _log.info(
            "nt_deploy_started",
            deployment_instance_id=deployment_instance_id,
            spec_id=spec_id,
            trading_mode=trading_mode,
            connector=spec.get("connector"),
            permission_scope=credential.get("permission_scope"),
            strategy=type(strategy).__name__,
        )
        return deployment_instance_id

    def _build_exec_plan(self, trading_mode: str, spec: dict, credential: dict, venue):
        """Resolve (exec_config, exec_factory, reconciliation) for the trading mode.

        sandbox fills locally against live prices (no exchange contact); testnet /
        live place real orders on the Binance testnet / live endpoints. Real venues
        reconcile against exchange account state, the sandbox has none. A live plan
        requires Crucible-signed promotion evidence inside the accepted spec.
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
                promotion_id=spec.get("promotion_id"),
            )
            exec_cfg = venue.build_exec_client_config_live(spec, credential)
            return exec_cfg, BinanceLiveExecClientFactory, True
        raise RuntimeError(
            f"unsupported trading_mode {trading_mode!r} (expected sandbox / testnet / live)"
        )

    def _attach_runtime_bridges(self, node, fact_context) -> None:
        msgbus = node.kernel.msgbus
        if fact_context is not None and self._runner_fact_emitter is not None:
            RunnerFactMessageBusBridge(
                emitter=self._runner_fact_emitter,
                deployment=fact_context[0],
            ).bootstrap(msgbus)

    def _build_runner_fact_context(self, spec: dict, credential: dict):
        if self._runner_fact_emitter is None or self._capability_receipt is None:
            return None
        strategy_id = spec.get("strategy_id")
        if not strategy_id:
            raise RuntimeError("validated DeploymentSpec lost its canonical strategy_id")
        spec_id = spec["spec_id"]
        deployment_instance_id = str(spec.get("deployment_instance_id") or "").strip()
        deployment_spec_digest = str(spec.get("deployment_spec_digest") or "").strip()
        if not deployment_instance_id or not deployment_spec_digest:
            raise RuntimeError(
                "validated DeploymentSpec lacks explicit DeploymentInstance/spec digest authority"
            )
        required_projectors = ["settlement", "risk", "health"]
        if spec["trading_mode"] in {"testnet", "live"}:
            required_projectors.append("reconciliation")
        self._capability_receipt.require_scope_bindings(
            projectors=required_projectors,
            trading_mode=str(spec["trading_mode"]),
            deployment_instance_id=deployment_instance_id,
            deployment_spec_id=spec_id,
            deployment_spec_digest=deployment_spec_digest,
            strategy_id=strategy_id,
        )
        authority = RunnerFactAuthority(
            tenant_id=self._tenant_id or "",
            trading_mode=str(spec["trading_mode"]),
            runner_id=self._capability_receipt.runner_id,
            deployment_instance_id=deployment_instance_id,
            deployment_spec_id=spec_id,
            deployment_spec_digest=deployment_spec_digest,
            strategy_id=strategy_id,
            capability_version_id=self._capability_receipt.capability_version_id,
            capability_version=self._capability_receipt.capability_version,
            capability_manifest_digest=self._capability_receipt.manifest_digest,
        )
        pairs = spec.get("pairs") or []
        currencies = {str(pair).upper().replace("/", "-").split("-")[-1] for pair in pairs}
        if len(currencies) != 1:
            raise RuntimeError("RunnerFact v1 requires one settlement currency per deployment")
        currency = next(iter(currencies))
        if currency not in SUPPORTED_CURRENCIES:
            raise RuntimeError(f"settlement currency {currency!r} is outside RunnerFact v1")
        provider = None
        if spec["trading_mode"] in {"testnet", "live"}:
            from custos.engines.nautilus.binance_ledger import BinanceVenueLedgerSource

            provider = BinanceVenueLedgerSource(spec=spec, credential=credential)
        deployment = RunnerFactDeployment(
            authority=authority,
            deployment_instance_id=deployment_instance_id,
            deployment_spec_id=str(spec_id),
            deployment_spec_digest=deployment_spec_digest,
            venue="BINANCE",
            currency=currency,
            reconciliation_available=provider is not None,
        )
        return deployment, provider

    async def stop(self, deployment_instance_id: str) -> None:
        self._peak_equity.pop(deployment_instance_id, None)
        self._runner_fact_contexts.pop(deployment_instance_id, None)
        entry = self._active_nodes.pop(deployment_instance_id, None)
        if entry is None:
            # Idempotent: stopping an unknown / already-stopped spec is a no-op.
            _log.info(
                "nt_stop_noop_unknown_instance",
                deployment_instance_id=deployment_instance_id,
            )
            return

        node, task = entry
        try:
            await asyncio.wait_for(node.stop_async(), timeout=self._stop_timeout_secs)
        except TimeoutError:
            _log.error(
                "nt_stop_timeout",
                deployment_instance_id=deployment_instance_id,
                timeout_secs=self._stop_timeout_secs,
            )
        finally:
            node.dispose()
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 — reaping the run task
                pass
        _log.info("nt_stop_completed", deployment_instance_id=deployment_instance_id)

    async def close(self) -> None:
        for deployment_instance_id in tuple(self._active_nodes):
            await self.stop(deployment_instance_id)

    def runner_fact_deployments(self) -> tuple[RunnerFactDeployment, ...]:
        return tuple(context[0] for context in self._runner_fact_contexts.values())

    async def runner_fact_risk_snapshot(
        self, deployment_instance_id: str, currency: str
    ) -> tuple[Decimal, list[dict]]:
        context = self._runner_fact_contexts.get(deployment_instance_id)
        entry = self._active_nodes.get(deployment_instance_id)
        if entry is None or context is None:
            raise RuntimeError(
                f"RunnerFact DeploymentInstance {deployment_instance_id!r} is not active"
            )
        node, _task = entry
        positions = list(node.kernel.cache.positions_open())
        venue = positions[0].instrument_id.venue if positions else None
        if venue is None:
            instrument_ids = sorted(node.kernel.cache.instrument_ids(), key=str)
            if not instrument_ids:
                raise RuntimeError("no instrument is cached for risk equity")
            venue = instrument_ids[0].venue
        equities = node.kernel.portfolio.equity(venue)
        if node.kernel.portfolio.missing_price_instruments(venue):
            raise RuntimeError("portfolio equity is incomplete because mark prices are missing")
        money = next(
            (value for key, value in (equities or {}).items() if str(key) == currency),
            None,
        )
        if money is None:
            raise RuntimeError(f"portfolio equity has no {currency} value")
        equity = Decimal(str(money.as_decimal()))
        rows: list[dict] = []
        for position in positions:
            mark_update = node.kernel.cache.mark_price(position.instrument_id)
            raw_mark = getattr(mark_update, "value", None) if mark_update is not None else None
            if raw_mark is None and PriceType is not None:
                raw_mark = node.kernel.cache.price(position.instrument_id, PriceType.MID)
            if raw_mark is None:
                raise RuntimeError(f"mark price unavailable for {position.instrument_id}")
            settlement = str(getattr(position, "settlement_currency", currency))
            signed_quantity = Decimal(str(position.quantity))
            if bool(position.is_short):
                signed_quantity = -signed_quantity
            rows.append(
                {
                    "instrument": str(position.instrument_id),
                    "quantity": str(signed_quantity),
                    "mark_price": str(raw_mark),
                    "currency": settlement,
                }
            )
        return equity, rows

    async def runner_fact_venue_ledger(
        self, deployment_instance_id: str, coverage_from, closed_at
    ) -> VenueLedgerEvidence:
        context = self._runner_fact_contexts.get(deployment_instance_id)
        if context is None or context[1] is None:
            raise RuntimeError("independent venue ledger is unavailable for this deployment")
        return await context[1].collect(coverage_from, closed_at)

    async def reconfigure(self, spec: dict) -> None:
        """v1 reconfigure: apply runtime-tunable params in place, reject structural.

        A running TradingNode cannot hot-swap its strategy class, venue, or traded
        symbols, so any structural change must go through stop + re-deploy (the
        reconciler owns the credential ref for that). Only changes the caller
        explicitly flags as runtime-tunable (leverage / notional cap) are accepted
        here; today they are logged as intent (live application is a follow-up).
        """
        deployment_instance_id = str(spec.get("deployment_instance_id") or "")
        reconfigure_spec = spec.get("reconfigure") or {}
        if reconfigure_spec.get("runtime_tunable_only"):
            _log.info(
                "nt_reconfigure_runtime_tunable",
                deployment_instance_id=deployment_instance_id,
                params=reconfigure_spec.get("params"),
            )
            return
        raise NotImplementedError(
            f"structural reconfigure of instance {deployment_instance_id!r} "
            "requires stop + re-deploy "
            "(v1 NtTradingNodeHost does not hot-swap strategy / venue / symbol)"
        )

    async def get_open_notional(self, deployment_instance_id: str) -> Decimal:
        """Total gross open notional across this spec's open positions, as Decimal.

        Reads the built node's cache; an unknown / not-yet-deployed spec has zero
        exposure. Quantity + entry price are stringified before Decimal
        conversion so no float reaches the money math (red line 0.4).
        """
        entry = self._active_nodes.get(deployment_instance_id)
        if entry is None:
            return Decimal("0")
        node, _task = entry
        total = Decimal("0")
        for position in node.kernel.cache.positions_open():
            quantity = abs(Decimal(str(position.quantity)))
            entry_px = Decimal(str(position.avg_px_open))
            total += quantity * entry_px
        return total

    async def check_engine_connected(self, deployment_instance_id: str) -> ConnectivityState:
        """Data + execution engine connectivity for this spec's node. An unknown
        / not-yet-deployed spec is reported disconnected — a spec the reconciler
        believes is running but has no live node is exactly the zombie case."""
        entry = self._active_nodes.get(deployment_instance_id)
        if entry is None:
            return ConnectivityState(
                data_connected=False, exec_connected=False, checked_at_epoch_s=time.time()
            )
        node, _task = entry
        return ConnectivityState(
            data_connected=bool(node.kernel.data_engine.check_connected()),
            exec_connected=bool(node.kernel.exec_engine.check_connected()),
            checked_at_epoch_s=time.time(),
        )

    async def flatten_positions(self, deployment_instance_id: str, reason: str) -> None:
        """Close every open position for this spec via NT's per-instrument
        ``Strategy.close_all_positions`` — the engine-neutral ``flatten_positions``
        name maps here (NT has no ``flatten_positions``). An unknown spec is a
        logged no-op."""
        entry = self._active_nodes.get(deployment_instance_id)
        if entry is None:
            _log.warning(
                "flatten_positions_unknown_instance",
                deployment_instance_id=deployment_instance_id,
                reason=reason,
            )
            return
        node, _task = entry
        instrument_ids = {position.instrument_id for position in node.kernel.cache.positions_open()}
        for strategy in node.kernel.trader.strategies():
            for instrument_id in instrument_ids:
                strategy.close_all_positions(instrument_id)
        _log.warning(
            "positions_flattened",
            deployment_instance_id=deployment_instance_id,
            reason=reason,
            instrument_count=len(instrument_ids),
        )

    async def get_positions(self, deployment_instance_id: str) -> list[PositionSnapshot]:
        """Materialise every open position as a Decimal-only ``PositionSnapshot``.

        Quantity, entry price and unrealized pnl are stringified before Decimal
        conversion so no float reaches the money math (red line 0.4). An
        unknown / not-yet-deployed spec has no positions.
        """

        entry = self._active_nodes.get(deployment_instance_id)
        if entry is None:
            return []
        node, _task = entry
        snapshots: list[PositionSnapshot] = []
        for position in node.kernel.cache.positions_open():
            quantity = Decimal(str(position.quantity))
            avg_px = Decimal(str(position.avg_px_open))
            unrealized = Decimal(str(getattr(position, "unrealized_pnl", "0")))
            snapshots.append(
                PositionSnapshot(
                    instrument_id=str(position.instrument_id),
                    quantity=quantity,
                    avg_px=avg_px,
                    unrealized_pnl=unrealized,
                    notional=abs(quantity) * avg_px,
                )
            )
        return snapshots

    async def get_orders(self, deployment_instance_id: str) -> list[OrderSnapshot]:
        """Materialise every open order as a Decimal-only ``OrderSnapshot``."""

        entry = self._active_nodes.get(deployment_instance_id)
        if entry is None:
            return []
        node, _task = entry
        snapshots: list[OrderSnapshot] = []
        for order in node.kernel.cache.orders_open():
            snapshots.append(
                OrderSnapshot(
                    client_order_id=str(order.client_order_id),
                    instrument_id=str(order.instrument_id),
                    side=str(order.side),
                    quantity=Decimal(str(order.quantity)),
                    price=Decimal(str(order.price)),
                    status=str(order.status),
                )
            )
        return snapshots

    async def get_engine_status(self, deployment_instance_id: str) -> EngineStatus:
        """Aggregate exposure + equity snapshot for the reconciler and the
        state-snapshot publisher.

        ``current_equity`` is a light-weight engine-side proxy — gross open
        notional plus every position's unrealized pnl. This is enough to feed
        the fallback breaker's drawdown check (which trips on peak-to-current
        percentage) without depending on a per-venue portfolio ledger that a
        stubbed test node does not expose. ``peak_equity`` is host-tracked as a
        Decimal (red line 0.4, no float high-water mark).
        """

        entry = self._active_nodes.get(deployment_instance_id)
        if entry is None:
            return EngineStatus(
                phase="unknown",
                position_count=0,
                order_count=0,
                open_notional=Decimal("0"),
                peak_equity=Decimal("0"),
                current_equity=Decimal("0"),
                drawdown_pct=Decimal("0"),
            )
        node, _task = entry
        positions = list(node.kernel.cache.positions_open())
        try:
            orders = list(node.kernel.cache.orders_open())
        except AttributeError:
            # Some cache fakes do not expose orders_open (positions-only tests).
            orders = []
        open_notional = Decimal("0")
        unrealized_total = Decimal("0")
        for position in positions:
            quantity = Decimal(str(position.quantity))
            avg_px = Decimal(str(position.avg_px_open))
            open_notional += abs(quantity) * avg_px
            unrealized_total += Decimal(str(getattr(position, "unrealized_pnl", "0")))
        current_equity = open_notional + unrealized_total
        peak = self._peak_equity.get(deployment_instance_id, Decimal("0"))
        if current_equity > peak:
            peak = current_equity
            self._peak_equity[deployment_instance_id] = peak
        if peak > 0 and current_equity < peak:
            drawdown_pct = (peak - current_equity) / peak * Decimal("100")
        else:
            drawdown_pct = Decimal("0")
        return EngineStatus(
            phase="running",
            position_count=len(positions),
            order_count=len(orders),
            open_notional=open_notional,
            peak_equity=peak,
            current_equity=current_equity,
            drawdown_pct=drawdown_pct,
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
    def _trader_id(deployment_instance_id: str) -> str:
        tag = "".join(ch for ch in deployment_instance_id if ch.isalnum())[:20] or "000"
        return f"CUSTOS-{tag}"

    def _on_node_task_done(self, deployment_instance_id: str, task) -> None:
        # A background node loop dying must never be silent — surface the error.
        # Also drop the registry entry so a self-terminated node doesn't linger;
        # guard on task identity so a re-deployed spec_id (new task) isn't cleared
        # by a stale callback.
        entry = self._active_nodes.get(deployment_instance_id)
        if entry is not None and entry[1] is task:
            self._active_nodes.pop(deployment_instance_id, None)
            self._runner_fact_contexts.pop(deployment_instance_id, None)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            _log.error(
                "nt_node_loop_failed",
                deployment_instance_id=deployment_instance_id,
                **_sanitize_exception(exc),
            )
