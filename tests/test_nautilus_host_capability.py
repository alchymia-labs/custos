"""Host capability declarations — the contract the G6 gate queries.

NoopHost is a paper/sim stub: it must declare it supports neither live nor any
venue, so the gate's fail-safe default keeps a stub off live venues. The real
NtTradingNodeHost declares live + the Binance connectors it actually wires.

No NautilusTrader dependency: capability answers are static declarations, so
they are unit-testable on a base install. A separate NT-gated drift guard
asserts the declared venue set stays in sync with the venue-config module.
"""

from __future__ import annotations

from custos.engines.nautilus.host import NoopHost, NtTradingNodeHost


def test_noophost_rejects_live_capability() -> None:
    # Fail-safe: the stub must never claim live capability, or the gate would
    # let a paper stub silently swallow live orders.
    assert NoopHost().supports_live() is False


def test_noophost_rejects_all_venues() -> None:
    host = NoopHost()
    assert host.supports_venue("binance") is False
    assert host.supports_venue("binance_perpetual") is False


def test_ntlivehost_declares_live() -> None:
    assert NtTradingNodeHost().supports_live() is True


def test_ntlivehost_venue_binance_supported() -> None:
    host = NtTradingNodeHost()
    assert host.supports_venue("binance") is True
    assert host.supports_venue("binance_perpetual") is True


def test_ntlivehost_venue_case_insensitive() -> None:
    # Connector strings arrive from the wire; capability check is case-folded so
    # "BINANCE" and "binance" both resolve (mirrors the gate's mode folding).
    assert NtTradingNodeHost().supports_venue("BINANCE") is True


def test_ntlivehost_venue_unknown_rejected() -> None:
    host = NtTradingNodeHost()
    assert host.supports_venue("okx") is False
    assert host.supports_venue("okx_perpetual") is False
