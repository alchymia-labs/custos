"""ExecutionEngineProtocol Tier-1 contract tests.

A fake implementation with all 5 methods passes isinstance; a fake missing
any required method fails isinstance (relaxed-double proving the protocol
is a live guard, not a dead branch).
"""

from __future__ import annotations

from decimal import Decimal

from custos.core.engine_protocol import ConnectivityState, ExecutionEngineProtocol


class _CompleteHost:
    async def deploy(self, spec: dict, credential: dict) -> str:
        return "cid"

    async def reconfigure(self, spec: dict) -> None:
        pass

    async def stop(self, spec_id: str) -> None:
        pass

    def supports_live(self) -> bool:
        return False

    def supports_venue(self, venue: str) -> bool:
        return False

    async def get_open_notional(self, spec_id: str) -> Decimal:
        return Decimal("0")

    async def check_engine_connected(self, spec_id: str) -> ConnectivityState:
        return ConnectivityState(data_connected=True, exec_connected=True, checked_at_epoch_s=0.0)

    async def flatten_positions(self, spec_id: str, reason: str) -> None:
        pass


class _MissingDeploy:
    async def reconfigure(self, spec: dict) -> None:
        pass

    async def stop(self, spec_id: str) -> None:
        pass

    def supports_live(self) -> bool:
        return False

    def supports_venue(self, venue: str) -> bool:
        return False


class _MissingSupportsLive:
    async def deploy(self, spec: dict, credential: dict) -> str:
        return "cid"

    async def reconfigure(self, spec: dict) -> None:
        pass

    async def stop(self, spec_id: str) -> None:
        pass

    def supports_venue(self, venue: str) -> bool:
        return False


def test_complete_host_satisfies_protocol() -> None:
    assert isinstance(_CompleteHost(), ExecutionEngineProtocol)


def test_missing_deploy_fails_protocol() -> None:
    assert not isinstance(_MissingDeploy(), ExecutionEngineProtocol)


def test_missing_supports_live_fails_protocol() -> None:
    assert not isinstance(_MissingSupportsLive(), ExecutionEngineProtocol)
