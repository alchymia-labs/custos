"""Binance venue-config helpers — pure functions from spec+credential to NT config.

Covers the failure-mode contract for the venue-assembly layer:
- missing api_key in the credential dict -> KeyError (fail-fast, no NT build)
- unsupported connector (non-binance) -> NotImplementedError (explicit reject)

Plus happy-path field assertions on the constructed NT config objects. Requires
the nt-runtime extra (NautilusTrader); skipped cleanly when it is absent.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

pytest.importorskip("nautilus_trader")

from nautilus_trader.adapters.binance.common.enums import (  # noqa: E402
    BinanceAccountType,
    BinanceEnvironment,
)
from nautilus_trader.model.identifiers import InstrumentId  # noqa: E402

from arx_runner._nt_binance_venue import (  # noqa: E402
    build_data_client_config,
    build_exec_client_config_sandbox,
    build_futures_leverages,
    build_instrument_ids,
)


def _spec(connector: str = "binance_perpetual") -> dict:
    return {
        "connector": connector,
        "pairs": ["BTC-USDT", "ETH-USDT"],
        "leverage": 3,
    }


def _credential() -> dict:
    return {
        "api_key": "test-key",
        "api_secret": "test-secret",
        "permission_scope": "trade_no_withdraw",
    }


def test_build_instrument_ids() -> None:
    ids = build_instrument_ids(_spec("binance_perpetual"))
    assert ids == frozenset(
        {
            InstrumentId.from_str("BTCUSDT-PERP.BINANCE"),
            InstrumentId.from_str("ETHUSDT-PERP.BINANCE"),
        }
    )


def test_build_instrument_ids_spot() -> None:
    ids = build_instrument_ids(_spec("binance"))
    assert ids == frozenset(
        {
            InstrumentId.from_str("BTCUSDT.BINANCE"),
            InstrumentId.from_str("ETHUSDT.BINANCE"),
        }
    )


def test_build_instrument_ids_singular_pair_fallback() -> None:
    ids = build_instrument_ids({"connector": "binance_perpetual", "pair": "SOL-USDT"})
    assert ids == frozenset({InstrumentId.from_str("SOLUSDT-PERP.BINANCE")})


def test_build_futures_leverages_keyed_by_instrument_id() -> None:
    leverages = build_futures_leverages(_spec("binance_perpetual"))
    assert leverages == {
        InstrumentId.from_str("BTCUSDT-PERP.BINANCE"): Decimal("3"),
        InstrumentId.from_str("ETHUSDT-PERP.BINANCE"): Decimal("3"),
    }


def test_build_data_client_config_perpetual() -> None:
    cfg = build_data_client_config(_spec("binance_perpetual"), _credential())
    assert cfg.api_key == "test-key"
    assert cfg.api_secret == "test-secret"
    assert cfg.account_type == BinanceAccountType.USDT_FUTURES
    assert cfg.environment == BinanceEnvironment.LIVE
    assert cfg.instrument_provider.load_all is False
    assert InstrumentId.from_str("BTCUSDT-PERP.BINANCE") in cfg.instrument_provider.load_ids


def test_build_data_client_config_spot() -> None:
    cfg = build_data_client_config(_spec("binance"), _credential())
    assert cfg.account_type == BinanceAccountType.SPOT


def test_build_exec_client_config_sandbox_futures() -> None:
    cfg = build_exec_client_config_sandbox(
        _spec("binance_perpetual"), _credential(), ["10_000 USDT"]
    )
    assert cfg.venue == "BINANCE"
    # NT config stores the enum field as its string name; node.build() rejects
    # the enum object, so the helper must emit "MARGIN"/"CASH" (regression guard).
    assert cfg.account_type == "MARGIN"
    assert cfg.starting_balances == ["10_000 USDT"]
    assert cfg.leverages == {
        InstrumentId.from_str("BTCUSDT-PERP.BINANCE"): Decimal("3"),
        InstrumentId.from_str("ETHUSDT-PERP.BINANCE"): Decimal("3"),
    }


def test_build_exec_client_config_sandbox_spot_is_cash() -> None:
    cfg = build_exec_client_config_sandbox(_spec("binance"), _credential(), ["10_000 USDT"])
    assert cfg.account_type == "CASH"


def test_missing_api_key_raises() -> None:
    # Failure-mode contract: credential without api_key -> KeyError (fail-fast).
    bad_credential = {"api_secret": "s", "permission_scope": "trade_no_withdraw"}
    with pytest.raises(KeyError):
        build_data_client_config(_spec("binance_perpetual"), bad_credential)


def test_unsupported_connector_notimpl() -> None:
    # Failure-mode contract: non-binance connector -> NotImplementedError (explicit).
    with pytest.raises(NotImplementedError, match="okx"):
        build_data_client_config(_spec("okx_perpetual"), _credential())
