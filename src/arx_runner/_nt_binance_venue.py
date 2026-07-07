"""Binance venue-config assembly (pure functions, no IO, no side effects).

Turns a DeploymentSpec parameter dict + a decrypted credential dict into
NautilusTrader client-config objects. Sandbox mode pairs a real-time Binance
*data* feed with a locally simulated *execution* venue
(``SandboxExecutionClientConfig`` + ``SandboxLiveExecClientFactory``), so no
real orders reach the exchange.

non-custodial 红线 0.1: this module only forwards the caller-supplied
credential fields into NT config objects and returns them. It never logs,
prints, or publishes credential material — keep it that way.

Only Binance (spot + USDT-perpetual) is wired here; other venues are rejected
explicitly. Testnet / live promotion is a later plan; sandbox data uses the
LIVE Binance feed because simulated execution needs real prices.
"""

from __future__ import annotations

from decimal import Decimal

from nautilus_trader.adapters.binance.common.enums import (
    BinanceAccountType,
    BinanceEnvironment,
)
from nautilus_trader.adapters.binance.config import BinanceDataClientConfig, BinanceKeyType
from nautilus_trader.adapters.sandbox.config import SandboxExecutionClientConfig
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.model.identifiers import InstrumentId

# NT config stores these enum fields as their string name (not the enum object);
# node.build() rejects the enum instances. Pass the names directly.
_ACCOUNT_TYPE_FUTURES = "MARGIN"
_ACCOUNT_TYPE_SPOT = "CASH"
_OMS_TYPE_NETTING = "NETTING"

BINANCE_VENUE = "BINANCE"

# connector name (spec.connector) -> "spot" | "futures". Extend here (never
# elsewhere) when a new Binance product line is supported.
_BINANCE_CONNECTORS: dict[str, str] = {
    "binance": "spot",
    "binance_perpetual": "futures",
}


def _binance_exchange_type(connector: str) -> str:
    """Resolve connector to spot/futures, rejecting non-Binance venues."""
    exchange_type = _BINANCE_CONNECTORS.get(connector)
    if exchange_type is None:
        raise NotImplementedError(
            f"connector {connector!r} is not supported — only Binance "
            f"({', '.join(sorted(_BINANCE_CONNECTORS))}) is wired in this runner"
        )
    return exchange_type


def _trading_pairs(spec: dict) -> list[str]:
    """Configured pairs (plural list, legacy singular fallback)."""
    pairs = spec.get("pairs")
    if isinstance(pairs, list) and pairs:
        return list(pairs)
    return [spec.get("pair", "BTC-USDT")]


def _format_instrument_id(pair: str, connector: str) -> str:
    """ "BTC-USDT" + connector -> NT instrument id string."""
    symbol = pair.replace("-", "")
    if _binance_exchange_type(connector) == "futures":
        return f"{symbol}-PERP.{BINANCE_VENUE}"
    return f"{symbol}.{BINANCE_VENUE}"


def build_instrument_ids(spec: dict) -> frozenset[InstrumentId]:
    """InstrumentId set for the configured pairs."""
    connector = spec["connector"]
    return frozenset(
        InstrumentId.from_str(_format_instrument_id(pair, connector))
        for pair in _trading_pairs(spec)
    )


def build_futures_leverages(spec: dict) -> dict[InstrumentId, Decimal]:
    """Per-instrument leverage map for the configured pairs.

    Keyed by InstrumentId with Decimal values so it drops straight into the
    sandbox exec config's ``leverages`` field (and any future Binance live
    exec config). Without pinning, the account default (e.g. 20x) would apply.
    """
    connector = spec["connector"]
    leverage = Decimal(str(spec.get("leverage", 1)))
    return {
        InstrumentId.from_str(_format_instrument_id(pair, connector)): leverage
        for pair in _trading_pairs(spec)
    }


def build_data_client_config(spec: dict, credential: dict) -> BinanceDataClientConfig:
    """Real-time Binance data feed config (sandbox uses live market data)."""
    connector = spec["connector"]
    exchange_type = _binance_exchange_type(connector)
    # Fail-fast on a malformed credential before any NT object is built.
    api_key = credential["api_key"]
    api_secret = credential["api_secret"]
    key_type = BinanceKeyType[str(credential.get("key_type", "HMAC")).upper()]
    account_type = (
        BinanceAccountType.USDT_FUTURES if exchange_type == "futures" else BinanceAccountType.SPOT
    )
    return BinanceDataClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        key_type=key_type,
        account_type=account_type,
        environment=BinanceEnvironment.LIVE,
        instrument_provider=InstrumentProviderConfig(
            load_all=False,
            load_ids=build_instrument_ids(spec),
        ),
    )


def build_exec_client_config_sandbox(
    spec: dict,
    credential: dict,
    starting_balances: list[str],
) -> SandboxExecutionClientConfig:
    """Locally simulated execution venue for sandbox mode.

    Sandbox exec fills orders against real-time prices without touching the
    exchange, so no live credential is used here — ``credential`` is accepted
    for signature parity with the (future) testnet/live builders.
    """
    connector = spec["connector"]
    exchange_type = _binance_exchange_type(connector)
    if exchange_type == "futures":
        account_type = _ACCOUNT_TYPE_FUTURES
        leverages = build_futures_leverages(spec)
    else:
        account_type = _ACCOUNT_TYPE_SPOT
        leverages = {}
    return SandboxExecutionClientConfig(
        venue=BINANCE_VENUE,
        starting_balances=starting_balances,
        account_type=account_type,
        oms_type=_OMS_TYPE_NETTING,
        leverages=leverages,
    )
