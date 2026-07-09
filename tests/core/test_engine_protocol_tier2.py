"""ExecutionEngineProtocol Tier-2 contract tests.

Both shipped hosts must still satisfy the protocol after each Tier-2 method is
added; a fake missing a Tier-2 method must fail isinstance (relaxed-double
proving the extended protocol stays a live guard, not a dead branch).
"""

from __future__ import annotations

from decimal import Decimal

from custos.core.engine_protocol import ExecutionEngineProtocol
from custos.engines.nautilus.host import NoopHost, NtTradingNodeHost


def _nt_host() -> NtTradingNodeHost:
    return NtTradingNodeHost(telemetry_client=None, tenant_id="t", runner_id="r")


async def test_get_open_notional_noophost_zero() -> None:
    assert await NoopHost().get_open_notional("spec-1") == Decimal("0")


async def test_get_open_notional_returns_decimal() -> None:
    noop_val = await NoopHost().get_open_notional("spec-1")
    nt_val = await _nt_host().get_open_notional("spec-x")
    assert isinstance(noop_val, Decimal)
    assert isinstance(nt_val, Decimal)


class _MissingGetOpenNotional:
    """Full Tier-1 surface but no Tier-2 ``get_open_notional``."""

    async def deploy(self, spec: dict, credential: dict) -> str:
        return "cid"

    async def reconfigure(self, spec: dict) -> None: ...

    async def stop(self, spec_id: str) -> None: ...

    def supports_live(self) -> bool:
        return False

    def supports_venue(self, venue: str) -> bool:
        return False


def test_both_hosts_still_isinstance_after_tier2() -> None:
    assert isinstance(NoopHost(), ExecutionEngineProtocol)
    assert isinstance(_nt_host(), ExecutionEngineProtocol)
    # relaxed-double: dropping a Tier-2 method must break the isinstance check,
    # so the extended protocol is proven a live guard.
    assert not isinstance(_MissingGetOpenNotional(), ExecutionEngineProtocol)
