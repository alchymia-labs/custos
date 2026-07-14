"""Assert both shipped NT hosts implement ExecutionEngineProtocol."""

from __future__ import annotations

from custos.core.engine_protocol import ExecutionEngineProtocol
from custos.engines.nautilus.host import NoopHost, NtTradingNodeHost


def test_noophost_implements_protocol() -> None:
    assert isinstance(NoopHost(), ExecutionEngineProtocol)


def test_nt_trading_node_host_implements_protocol() -> None:
    host = NtTradingNodeHost(
        tenant_id="test",
        runner_id="r1",
    )
    assert isinstance(host, ExecutionEngineProtocol)
