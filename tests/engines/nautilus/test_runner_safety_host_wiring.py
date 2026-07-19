from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

pytest.importorskip("nautilus_trader")

from nautilus_trader.adapters.sandbox.factory import (  # noqa: E402
    SandboxLiveExecClientFactory,
)
from nautilus_trader.config import (  # noqa: E402
    LiveExecEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.live.factories import LiveExecClientFactory  # noqa: E402
from nautilus_trader.live.node import TradingNode  # noqa: E402
from nautilus_trader.model.identifiers import TraderId  # noqa: E402

from custos.engines.nautilus.host import NtTradingNodeHost  # noqa: E402
from custos.engines.nautilus.runner_safety import (  # noqa: E402
    GuardedLiveExecutionClient,
    RunnerReservationBoundary,
    guarded_exec_client_factory,
)
from custos.engines.nautilus.venue_binance import (  # noqa: E402
    BINANCE_VENUE,
    build_exec_client_config_sandbox,
)


class _ExecFactory(LiveExecClientFactory):
    @staticmethod
    def create(**kwargs):
        return SimpleNamespace(kwargs=kwargs)


class _Boundary:
    def __init__(self) -> None:
        self.message_bus = None

    def bootstrap(self, message_bus) -> None:
        self.message_bus = message_bus


def test_host_replaces_the_execution_factory_and_attaches_the_same_boundary() -> None:
    boundary = _Boundary()
    host = NtTradingNodeHost(
        runner_safety_boundary_factory=lambda spec: (
            boundary if spec["deployment_instance_id"] == "instance-1" else None
        )
    )

    factory, selected_boundary = host._build_guarded_exec_plan(
        _ExecFactory,
        {"deployment_instance_id": "instance-1"},
    )
    message_bus = object()
    node = SimpleNamespace(kernel=SimpleNamespace(msgbus=message_bus))
    host._attach_runtime_bridges(node, None, selected_boundary)

    assert factory is not _ExecFactory
    assert issubclass(factory, LiveExecClientFactory)
    assert selected_boundary is boundary
    assert boundary.message_bus is message_bus


def test_host_preserves_the_upstream_factory_without_runtime_boundary() -> None:
    host = NtTradingNodeHost()

    factory, boundary = host._build_guarded_exec_plan(
        _ExecFactory,
        {"deployment_instance_id": "instance-2"},
    )

    assert factory is _ExecFactory
    assert boundary is None


def test_real_sandbox_builder_registers_the_guarded_client_without_network() -> None:
    class _Store:
        pass

    spec = {
        "connector": "binance_perpetual",
        "pairs": ["BTC-USDT"],
        "sandbox": {"starting_balances": ["10_000 USDT"]},
    }
    config = TradingNodeConfig(
        trader_id=TraderId("TRADER-001"),
        logging=LoggingConfig(log_level="ERROR"),
        exec_clients={
            BINANCE_VENUE: build_exec_client_config_sandbox(
                spec,
                {},
                ["10_000 USDT"],
            )
        },
        exec_engine=LiveExecEngineConfig(reconciliation=False),
    )
    boundary = RunnerReservationBoundary(
        store=_Store(),
        deployment_instance_id=UUID("11111111-1111-4111-8111-111111111111"),
        policy_id=UUID("22222222-2222-4222-8222-222222222222"),
    )
    factory = guarded_exec_client_factory(SandboxLiveExecClientFactory, boundary)
    node = TradingNode(config=config)

    try:
        node.add_exec_client_factory(BINANCE_VENUE, factory)
        node.build()
        clients = tuple(node.kernel.exec_engine._clients.values())

        assert len(clients) == 1
        assert isinstance(clients[0], GuardedLiveExecutionClient)
        assert str(clients[0].id) == "BINANCE"
        assert factory.__name__ == "SandboxLiveExecClientFactory"
    finally:
        node.dispose()
