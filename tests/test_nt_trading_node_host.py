"""NtTradingNodeHost — deploy / stop / reconfigure unit tests.

Uses a fake TradingNode (no network, no real NT engine loop) to drive the host
control flow, plus a real self-contained NT strategy fixture for the load path.
The real-NT end-to-end assembly is covered in
test_nt_trading_node_host_integration.py.

Failure-mode contract (plan §失败模式覆盖契约表):
- NT extra missing -> RuntimeError with install hint (test_deploy_missing_nt_extra_fails_fast)
- TradingNode.build() raises -> nt_startup_failure logged + re-raised
- stop() unknown spec_id -> idempotent no-op
- stop() when stop_async hangs -> timeout forces dispose (nt_stop_timeout)
- reconfigure() structural change -> NotImplementedError
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import structlog

pytest.importorskip("nautilus_trader")

from nautilus_trader.adapters.binance.factories import BinanceLiveExecClientFactory  # noqa: E402
from nautilus_trader.adapters.sandbox.factory import SandboxLiveExecClientFactory  # noqa: E402

from arx_runner import nautilus_host  # noqa: E402
from arx_runner.nautilus_host import NtTradingNodeHost  # noqa: E402

_FIXTURE_STRATEGY = Path(__file__).parent / "fixtures" / "minimal_supertrend_strategy.py"


def _spec(spec_id: str = "spec-1", **overrides) -> dict:
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


class _FakeTrader:
    def __init__(self) -> None:
        self.strategies: list = []

    def add_strategy(self, strategy) -> None:
        self.strategies.append(strategy)


class _FakeMsgBus:
    def __init__(self) -> None:
        self.subscriptions: list = []

    def subscribe(self, topic, handler) -> None:
        self.subscriptions.append((topic, handler))


class _FakeKernel:
    def __init__(self) -> None:
        self.msgbus = _FakeMsgBus()


class _FakeTradingNode:
    """Stand-in for nautilus_trader TradingNode: records calls, no network."""

    instances: list = []

    def __init__(self, config) -> None:
        self.config = config
        self.built = False
        self.disposed = False
        self.data_factories: list = []
        self.exec_factories: list = []
        self.trader = _FakeTrader()
        self.kernel = _FakeKernel()
        self._stop = asyncio.Event()
        self.build_raises = False
        self.build_error_msg = "nt build boom"
        self.stop_hangs = False
        _FakeTradingNode.instances.append(self)

    def add_data_client_factory(self, name, factory) -> None:
        self.data_factories.append((name, factory))

    def add_exec_client_factory(self, name, factory) -> None:
        self.exec_factories.append((name, factory))

    def build(self) -> None:
        if self.build_raises:
            raise RuntimeError(self.build_error_msg)
        self.built = True

    async def run_async(self) -> None:
        await self._stop.wait()

    async def stop_async(self) -> None:
        if self.stop_hangs:
            await asyncio.Event().wait()  # never resolves
        self._stop.set()

    def dispose(self) -> None:
        self.disposed = True


@pytest.fixture(autouse=True)
def _reset_fake_nodes():
    _FakeTradingNode.instances.clear()
    yield
    _FakeTradingNode.instances.clear()


@pytest.mark.asyncio
async def test_deploy_missing_nt_extra_fails_fast(monkeypatch) -> None:
    monkeypatch.setattr(nautilus_host, "TradingNode", None)
    host = NtTradingNodeHost()
    with pytest.raises(RuntimeError, match="nt-runtime"):
        await host.deploy(_spec(), _credential())


@pytest.mark.asyncio
async def test_build_failure_records_startup_error(monkeypatch) -> None:
    def _factory(config):
        node = _FakeTradingNode(config)
        node.build_raises = True
        return node

    monkeypatch.setattr(nautilus_host, "TradingNode", _factory)
    host = NtTradingNodeHost()
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(RuntimeError, match="nt build boom"):
            await host.deploy(_spec(), _credential())
    assert "nt_startup_failure" in [e.get("event") for e in logs]
    # failed deploy must not leave a registered node
    assert host._active_nodes == {}


@pytest.mark.asyncio
async def test_deploy_sandbox_success(monkeypatch) -> None:
    monkeypatch.setattr(nautilus_host, "TradingNode", _FakeTradingNode)
    host = NtTradingNodeHost()
    container_id = await host.deploy(_spec("spec-42"), _credential())
    try:
        assert container_id == "spec-42"
        assert "spec-42" in host._active_nodes
        node = _FakeTradingNode.instances[-1]
        assert node.built is True
        # sandbox exec + binance data factories registered under the venue name
        assert [n for n, _ in node.exec_factories] == ["BINANCE"]
        assert [n for n, _ in node.data_factories] == ["BINANCE"]
        # the self-contained fixture strategy was added
        assert node.trader.strategies
        assert type(node.trader.strategies[0]).__name__ == "MinimalSupertrendStrategy"
    finally:
        await host.stop("spec-42")


@pytest.mark.asyncio
async def test_deploy_sandbox_uses_sandbox_exec_factory(monkeypatch) -> None:
    # Mode dispatch: sandbox routes to the locally-simulated exec factory, never
    # a real Binance one (regression guard on the mode fan-out).
    monkeypatch.setattr(nautilus_host, "TradingNode", _FakeTradingNode)
    host = NtTradingNodeHost()
    await host.deploy(_spec("sb-1", trading_mode="sandbox"), _credential())
    try:
        node = _FakeTradingNode.instances[-1]
        assert node.exec_factories[0][1] is SandboxLiveExecClientFactory
    finally:
        await host.stop("sb-1")


@pytest.mark.asyncio
async def test_deploy_testnet_uses_binance_exec_factory(monkeypatch) -> None:
    # testnet routes to the real Binance exec factory (against the testnet endpoint),
    # not the sandbox simulator.
    monkeypatch.setattr(nautilus_host, "TradingNode", _FakeTradingNode)
    host = NtTradingNodeHost()
    await host.deploy(_spec("tn-1", trading_mode="testnet"), _credential())
    try:
        node = _FakeTradingNode.instances[-1]
        assert node.exec_factories[0][1] is BinanceLiveExecClientFactory
        assert node.exec_factories[0][1] is not SandboxLiveExecClientFactory
    finally:
        await host.stop("tn-1")


@pytest.mark.asyncio
async def test_deploy_live_success_with_approvers(monkeypatch) -> None:
    monkeypatch.setattr(nautilus_host, "TradingNode", _FakeTradingNode)
    host = NtTradingNodeHost()
    spec = _spec("live-ok", trading_mode="live", approved_by=["alice", "bob"])
    with structlog.testing.capture_logs() as logs:
        await host.deploy(spec, _credential())
    try:
        node = _FakeTradingNode.instances[-1]
        assert node.exec_factories[0][1] is BinanceLiveExecClientFactory
        assert "nt_live_deploy_requested" in [e.get("event") for e in logs]
    finally:
        await host.stop("live-ok")


@pytest.mark.asyncio
async def test_deploy_live_rejects_missing_approvers(monkeypatch) -> None:
    # Separation of duties: a live deploy without >= 2 approvers is refused before
    # any node is constructed (sod_approval_missing).
    monkeypatch.setattr(nautilus_host, "TradingNode", _FakeTradingNode)
    host = NtTradingNodeHost()
    with pytest.raises(RuntimeError, match="sod_approval_missing"):
        await host.deploy(_spec("live-bad", trading_mode="live"), _credential())
    assert _FakeTradingNode.instances == []
    assert host._active_nodes == {}


@pytest.mark.asyncio
async def test_deploy_unknown_trading_mode_rejected(monkeypatch) -> None:
    # An unrecognised trading_mode is refused at dispatch (no silent fallback to a
    # default execution path), before any node is constructed.
    monkeypatch.setattr(nautilus_host, "TradingNode", _FakeTradingNode)
    host = NtTradingNodeHost()
    with pytest.raises(RuntimeError, match="unsupported trading_mode"):
        await host.deploy(_spec("weird-1", trading_mode="paper_trading"), _credential())
    assert _FakeTradingNode.instances == []
    assert host._active_nodes == {}


@pytest.mark.asyncio
async def test_deploy_does_not_retain_credential(monkeypatch) -> None:
    # non-custodial 红线 0.1: credential must not live in host state after deploy.
    monkeypatch.setattr(nautilus_host, "TradingNode", _FakeTradingNode)
    host = NtTradingNodeHost()
    cred = _credential()
    await host.deploy(_spec("spec-7"), cred)
    try:
        state_blob = repr(host._active_nodes)
        assert "test-key" not in state_blob
        assert "test-secret" not in state_blob
    finally:
        await host.stop("spec-7")


@pytest.mark.asyncio
async def test_stop_idempotent() -> None:
    # Failure-mode contract: stopping an unknown spec_id is a no-op, not an error.
    host = NtTradingNodeHost()
    with structlog.testing.capture_logs() as logs:
        await host.stop("never-deployed")
    assert "nt_stop_noop_unknown_spec" in [e.get("event") for e in logs]


@pytest.mark.asyncio
async def test_stop_timeout_forces_dispose(monkeypatch) -> None:
    # Failure-mode contract: a hung stop_async times out, then dispose is forced.
    monkeypatch.setattr(nautilus_host, "TradingNode", _FakeTradingNode)
    host = NtTradingNodeHost()
    host._stop_timeout_secs = 0.05
    await host.deploy(_spec("spec-hang"), _credential())
    node = host._active_nodes["spec-hang"][0]
    node.stop_hangs = True
    with structlog.testing.capture_logs() as logs:
        await host.stop("spec-hang")
    assert "nt_stop_timeout" in [e.get("event") for e in logs]
    assert node.disposed is True
    assert "spec-hang" not in host._active_nodes


@pytest.mark.asyncio
async def test_reconfigure_structural_raises() -> None:
    # Failure-mode contract: structural reconfigure is rejected (needs re-deploy).
    host = NtTradingNodeHost()
    with pytest.raises(NotImplementedError, match="re-deploy"):
        await host.reconfigure(_spec("spec-x", connector="binance"))


@pytest.mark.asyncio
async def test_reconfigure_runtime_tunable_logs() -> None:
    # relaxed double: the runtime-tunable branch is a live path, not a dead one.
    host = NtTradingNodeHost()
    spec = {
        "spec_id": "spec-y",
        "reconfigure": {"runtime_tunable_only": True, "params": {"leverage": 5}},
    }
    with structlog.testing.capture_logs() as logs:
        await host.reconfigure(spec)
    assert "nt_reconfigure_runtime_tunable" in [e.get("event") for e in logs]


@pytest.mark.asyncio
async def test_exception_log_redacts_credential_material(monkeypatch) -> None:
    # non-custodial 红线 0.1: an exception message that could carry credential
    # material must be redacted before it reaches the log.
    def _factory(config):
        node = _FakeTradingNode(config)
        node.build_raises = True
        node.build_error_msg = "connection failed with api_key=REAL_SECRET_KEY"
        return node

    monkeypatch.setattr(nautilus_host, "TradingNode", _factory)
    host = NtTradingNodeHost()
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(RuntimeError):
            await host.deploy(_spec(), _credential())
    startup = [e for e in logs if e.get("event") == "nt_startup_failure"]
    assert startup
    assert "REAL_SECRET_KEY" not in str(startup[0])
    assert "redacted" in startup[0].get("error", "")
    assert startup[0].get("error_type") == "RuntimeError"


@pytest.mark.asyncio
async def test_exception_log_passthrough_when_no_credential(monkeypatch) -> None:
    # Redaction is targeted, not blanket: a benign message is preserved for triage.
    def _factory(config):
        node = _FakeTradingNode(config)
        node.build_raises = True
        node.build_error_msg = "instrument BTCUSDT-PERP.BINANCE not found"
        return node

    monkeypatch.setattr(nautilus_host, "TradingNode", _factory)
    host = NtTradingNodeHost()
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(RuntimeError):
            await host.deploy(_spec(), _credential())
    startup = [e for e in logs if e.get("event") == "nt_startup_failure"]
    assert startup
    assert startup[0].get("error") == "instrument BTCUSDT-PERP.BINANCE not found"
    assert startup[0].get("error_type") == "RuntimeError"


@pytest.mark.asyncio
async def test_deploy_duplicate_spec_id_raises(monkeypatch) -> None:
    # Re-deploying a live spec_id is rejected (must stop first) — never silent replace.
    monkeypatch.setattr(nautilus_host, "TradingNode", _FakeTradingNode)
    host = NtTradingNodeHost()
    await host.deploy(_spec("dup-1"), _credential())
    try:
        with pytest.raises(RuntimeError, match="already deployed"):
            await host.deploy(_spec("dup-1"), _credential())
        # original node untouched; the duplicate never constructed a second node
        assert len(_FakeTradingNode.instances) == 1
        assert "dup-1" in host._active_nodes
    finally:
        await host.stop("dup-1")


@pytest.mark.asyncio
async def test_task_done_callback_cleans_active_entry(monkeypatch) -> None:
    # A self-terminated node run task removes its own registry entry (no stale leak).
    monkeypatch.setattr(nautilus_host, "TradingNode", _FakeTradingNode)
    host = NtTradingNodeHost()
    await host.deploy(_spec("self-term"), _credential())
    node, task = host._active_nodes["self-term"]
    node._stop.set()  # end the run loop without going through stop()
    await task
    await asyncio.sleep(0.01)  # let the done-callback run
    assert "self-term" not in host._active_nodes


def _telemetry_client():
    from arx_runner.nats_client import ArxNatsClient

    return ArxNatsClient(nats_url="nats://localhost:4222", tenant_id="acme", runner_id="runner-7")


@pytest.mark.asyncio
async def test_deploy_attaches_telemetry_and_risk_bridge(monkeypatch) -> None:
    # A host constructed with a telemetry client attaches the telemetry bridge
    # (events.order.* + events.position.*) and the pre-trade reject bridge
    # (events.order.*) to the built node's MessageBus, and starts the actor.
    monkeypatch.setattr(nautilus_host, "TradingNode", _FakeTradingNode)
    host = NtTradingNodeHost(
        telemetry_client=_telemetry_client(), tenant_id="acme", runner_id="runner-7"
    )
    await host.deploy(_spec("obs-1"), _credential())
    try:
        node = _FakeTradingNode.instances[-1]
        topics = [t for t, _ in node.kernel.msgbus.subscriptions]
        assert topics.count("events.order.*") == 2  # telemetry fill filter + risk denial filter
        assert "events.position.*" in topics
        # telemetry actor is live (registered + running flush loop)
        assert "obs-1" in host._telemetry_actors
        assert host._telemetry_actors["obs-1"]._flush_task is not None
    finally:
        await host.stop("obs-1")


@pytest.mark.asyncio
async def test_deploy_survives_telemetry_attach_failure(monkeypatch) -> None:
    # 红线 0.3: observability is secondary to the trade path. If attach fails
    # (here: the MessageBus is unavailable), deploy logs telemetry_actor_attach_failed
    # and still completes — the node runs, telemetry is simply not attached.
    def _factory(config):
        node = _FakeTradingNode(config)
        node.kernel.msgbus = None  # attach will fail-fast on a None bus
        return node

    monkeypatch.setattr(nautilus_host, "TradingNode", _factory)
    host = NtTradingNodeHost(
        telemetry_client=_telemetry_client(), tenant_id="acme", runner_id="runner-7"
    )
    with structlog.testing.capture_logs() as logs:
        container_id = await host.deploy(_spec("obs-fail"), _credential())
    try:
        assert container_id == "obs-fail"
        assert "obs-fail" in host._active_nodes  # deploy still succeeded
        assert "obs-fail" not in host._telemetry_actors  # no actor registered
        assert "telemetry_actor_attach_failed" in [e.get("event") for e in logs]
    finally:
        await host.stop("obs-fail")


@pytest.mark.asyncio
async def test_deploy_without_telemetry_client_skips_attach(monkeypatch) -> None:
    # A host without a telemetry client (G6 capability checks / unit tests) never
    # touches the MessageBus — attach is opt-in on telemetry wiring being present.
    monkeypatch.setattr(nautilus_host, "TradingNode", _FakeTradingNode)
    host = NtTradingNodeHost()
    await host.deploy(_spec("no-obs"), _credential())
    try:
        node = _FakeTradingNode.instances[-1]
        assert node.kernel.msgbus.subscriptions == []
        assert host._telemetry_actors == {}
    finally:
        await host.stop("no-obs")


@pytest.mark.asyncio
async def test_stop_stops_attached_telemetry_actor(monkeypatch) -> None:
    # stop() tears down the attached telemetry actor (drains + cancels its loops)
    # so a stopped deployment leaks no background tasks.
    monkeypatch.setattr(nautilus_host, "TradingNode", _FakeTradingNode)
    host = NtTradingNodeHost(
        telemetry_client=_telemetry_client(), tenant_id="acme", runner_id="runner-7"
    )
    await host.deploy(_spec("obs-stop"), _credential())
    actor = host._telemetry_actors["obs-stop"]
    await host.stop("obs-stop")
    assert "obs-stop" not in host._telemetry_actors
    assert actor._flush_task is None  # actor stopped its loops


@pytest.mark.asyncio
async def test_strategy_instantiate_failure_no_built_node_leak(monkeypatch) -> None:
    # A strategy-instantiation failure happens before the node is built, so no
    # built node is ever constructed or leaked.
    monkeypatch.setattr(nautilus_host, "TradingNode", _FakeTradingNode)

    def _boom(self, strategy_cls, spec):
        raise RuntimeError("strategy config boom")

    monkeypatch.setattr(NtTradingNodeHost, "_instantiate_strategy", _boom)
    host = NtTradingNodeHost()
    with pytest.raises(RuntimeError, match="strategy config boom"):
        await host.deploy(_spec("leak-check"), _credential())
    assert _FakeTradingNode.instances == []
    assert host._active_nodes == {}
