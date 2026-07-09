"""ExecutionEngineProtocol Tier-1 contract tests.

A fake implementation with all 5 methods passes isinstance; a fake missing
any required method fails isinstance (relaxed-double proving the protocol
is a live guard, not a dead branch).
"""

from __future__ import annotations

from custos.core.engine_protocol import ExecutionEngineProtocol


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
