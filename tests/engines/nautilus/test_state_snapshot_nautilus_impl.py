"""NtTradingNodeHost Tier-2 implementations against a stubbed NT node.

These drive the real host methods with a lightweight fake node/kernel/cache so
the position/connectivity/flatten mappings are exercised without a running
TradingNode. Money is asserted Decimal end to end (red line 0.4).
"""

from __future__ import annotations

from decimal import Decimal

from custos.engines.nautilus.host import NoopHost, NtTradingNodeHost


class _FakePosition:
    def __init__(self, quantity: str, avg_px_open: str) -> None:
        self.quantity = quantity
        self.avg_px_open = avg_px_open


class _FakeCache:
    def __init__(self, positions: list[_FakePosition]) -> None:
        self._positions = positions

    def positions_open(self) -> list[_FakePosition]:
        return self._positions


class _FakeKernel:
    def __init__(self, cache: _FakeCache) -> None:
        self.cache = cache


class _FakeNode:
    def __init__(self, positions: list[_FakePosition]) -> None:
        self.kernel = _FakeKernel(_FakeCache(positions))


def _host() -> NtTradingNodeHost:
    return NtTradingNodeHost(telemetry_client=None, tenant_id="t", runner_id="r")


async def test_nt_host_get_open_notional_sums_positions_decimal() -> None:
    host = _host()
    node = _FakeNode([_FakePosition("2", "100"), _FakePosition("-1", "50")])
    host._active_nodes["spec-1"] = (node, None)

    value = await host.get_open_notional("spec-1")

    # 2 * 100 + abs(-1) * 50 = 250, gross exposure over both legs.
    assert value == Decimal("250")
    assert isinstance(value, Decimal)


async def test_nt_host_get_open_notional_unknown_spec_zero() -> None:
    assert await _host().get_open_notional("nope") == Decimal("0")


# -- flatten_positions → NT close_all_positions mapping -------------------


class _FakeStrategy:
    def __init__(self) -> None:
        self.closed: list = []

    def close_all_positions(self, instrument_id) -> None:
        self.closed.append(instrument_id)


class _FakeInstPosition:
    def __init__(self, instrument_id: str) -> None:
        self.instrument_id = instrument_id


class _FakeTrader:
    def __init__(self, strategies: list) -> None:
        self._strategies = strategies

    def strategies(self) -> list:
        return self._strategies


class _FakeFlattenCache:
    def __init__(self, positions: list) -> None:
        self._positions = positions

    def positions_open(self) -> list:
        return self._positions


class _FakeFlattenKernel:
    def __init__(self, positions: list, strategies: list) -> None:
        self.cache = _FakeFlattenCache(positions)
        self.trader = _FakeTrader(strategies)


class _FakeFlattenNode:
    def __init__(self, positions: list, strategies: list) -> None:
        self.kernel = _FakeFlattenKernel(positions, strategies)


async def test_flatten_positions_maps_to_close_all() -> None:
    host = _host()
    strategy = _FakeStrategy()
    node = _FakeFlattenNode(
        [_FakeInstPosition("BTCUSDT"), _FakeInstPosition("ETHUSDT")], [strategy]
    )
    host._active_nodes["spec-1"] = (node, None)

    await host.flatten_positions("spec-1", "notional_breach")

    # The engine-neutral flatten maps to NT's per-instrument close_all_positions.
    assert sorted(strategy.closed) == ["BTCUSDT", "ETHUSDT"]


async def test_flatten_positions_noophost_noop() -> None:
    # A paper host flatten is a logged no-op — no exception, no state.
    await NoopHost().flatten_positions("spec-1", "notional_breach")
