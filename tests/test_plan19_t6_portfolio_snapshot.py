from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from custos.engines.nautilus.host import NtTradingNodeHost
from custos.engines.nautilus.portfolio_snapshot import (
    NautilusPortfolioPosition,
    NautilusPortfolioSnapshot,
    NautilusPortfolioSnapshotProvider,
)


class _DecimalValue:
    def __init__(self, value: str) -> None:
        self._value = value

    def as_decimal(self) -> Decimal:
        return Decimal(self._value)

    def __str__(self) -> str:
        return self._value


class _InstrumentId:
    venue = "BINANCE"

    def __init__(self, value: str = "BTC-USDT.BINANCE") -> None:
        self._value = value

    def __str__(self) -> str:
        return self._value


class _Position:
    def __init__(self) -> None:
        self.instrument_id = _InstrumentId()
        self.quantity = _DecimalValue("2")
        self.avg_px_open = _DecimalValue("90")
        self.settlement_currency = "USDT"
        self.is_short = False
        self.mark_arguments: list[object] = []

    def unrealized_pnl(self, mark_price: object) -> _DecimalValue:
        self.mark_arguments.append(mark_price)
        return _DecimalValue("20")


class _Cache:
    def __init__(self, *, mark_price: object | None) -> None:
        self.position = _Position()
        self._mark_price = mark_price

    def positions_open(self):
        return [self.position]

    def instrument_ids(self):
        return [self.position.instrument_id]

    def mark_price(self, instrument_id):
        return self._mark_price

    def price(self, instrument_id, price_type):
        return None

    def orders_open(self):
        return []


class _Portfolio:
    def __init__(self, equities: dict | None = None, missing: tuple = ()) -> None:
        self._equities = equities if equities is not None else {"USDT": _DecimalValue("1000")}
        self._missing = missing
        self.venues: list[object] = []

    def equity(self, venue):
        self.venues.append(venue)
        return self._equities

    def missing_price_instruments(self, venue):
        return self._missing


class _Node:
    def __init__(self, *, mark_price: object | None, portfolio: _Portfolio | None = None) -> None:
        self.kernel = type(
            "Kernel",
            (),
            {
                "cache": _Cache(mark_price=mark_price),
                "portfolio": portfolio or _Portfolio(),
            },
        )()


def test_provider_calls_unrealized_pnl_with_trusted_mark_without_conversion_syntax() -> None:
    mark = _DecimalValue("100")
    node = _Node(mark_price=mark)
    snapshot = NautilusPortfolioSnapshotProvider(price_type_mid="MID").snapshot(
        node,
        currency="USDT",
    )

    assert snapshot.reliable is True
    assert snapshot.equity == Decimal("1000")
    assert snapshot.open_notional == Decimal("200")
    assert snapshot.positions[0].unrealized_pnl == Decimal("20")
    assert node.kernel.cache.position.mark_arguments == [mark]


def test_missing_mark_or_equity_returns_typed_unreliable_snapshot() -> None:
    missing_mark = NautilusPortfolioSnapshotProvider(price_type_mid="MID").snapshot(
        _Node(mark_price=None),
        currency="USDT",
    )
    missing_equity = NautilusPortfolioSnapshotProvider(price_type_mid="MID").snapshot(
        _Node(mark_price=_DecimalValue("100"), portfolio=_Portfolio(equities={})),
        currency="USDT",
    )

    assert missing_mark.reliable is False
    assert missing_mark.unreliable_reason == "mark_price_unavailable:BTC-USDT.BINANCE"
    assert missing_equity.reliable is False
    assert missing_equity.unreliable_reason == "portfolio_equity_missing:USDT"


@dataclass
class _RecordingProvider:
    value: NautilusPortfolioSnapshot

    def __post_init__(self) -> None:
        self.calls: list[str | None] = []

    def snapshot(self, node: object, *, currency: str | None = None) -> NautilusPortfolioSnapshot:
        self.calls.append(currency)
        return self.value


async def test_host_status_breaker_inputs_and_runner_facts_share_one_provider() -> None:
    position = NautilusPortfolioPosition(
        instrument_id="BTC-USDT.BINANCE",
        settlement_currency="USDT",
        quantity=Decimal("2"),
        avg_px=Decimal("90"),
        mark_price=Decimal("100"),
        unrealized_pnl=Decimal("20"),
        notional=Decimal("200"),
    )
    snapshot = NautilusPortfolioSnapshot(
        venue="BINANCE",
        currency="USDT",
        equity=Decimal("1000"),
        positions=(position,),
        reliable=True,
        unreliable_reason=None,
    )
    provider = _RecordingProvider(snapshot)
    host = NtTradingNodeHost(
        tenant_id="tenant",
        runner_id="runner",
        portfolio_snapshot_provider=provider,
    )
    node = _Node(mark_price=_DecimalValue("100"))
    host._active_nodes["instance"] = (node, None)
    host._runner_fact_contexts["instance"] = (object(), None)

    assert await host.get_open_notional("instance") == Decimal("200")
    assert (await host.get_positions("instance"))[0].unrealized_pnl == Decimal("20")
    status = await host.get_engine_status("instance")
    equity, rows = await host.runner_fact_risk_snapshot("instance", "USDT")

    assert status.reliable is True
    assert status.current_equity == Decimal("1000")
    assert equity == Decimal("1000")
    assert rows == [
        {
            "instrument": "BTC-USDT.BINANCE",
            "quantity": "2",
            "mark_price": "100",
            "currency": "USDT",
        }
    ]
    assert provider.calls == [None, None, None, "USDT"]


async def test_host_marks_inactive_or_unreliable_status_fail_closed() -> None:
    host = NtTradingNodeHost(tenant_id="tenant", runner_id="runner")
    inactive = await host.get_engine_status("missing")
    assert inactive.reliable is False
    assert inactive.unreliable_reason == "deployment_not_active"

    provider = _RecordingProvider(
        NautilusPortfolioSnapshot.unreliable("portfolio_equity_invalid")
    )
    host = NtTradingNodeHost(
        tenant_id="tenant",
        runner_id="runner",
        portfolio_snapshot_provider=provider,
    )
    host._active_nodes["instance"] = (_Node(mark_price=None), None)
    status = await host.get_engine_status("instance")
    assert status.phase == "degraded"
    assert status.reliable is False
    assert status.unreliable_reason == "portfolio_equity_invalid"
