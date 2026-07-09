"""
Signal configuration for OKX Signal Bot compatibility.

Provides configuration for external signal processing and OKX Signal Bot integration.
"""

import msgspec


class OkxConfig(msgspec.Struct, frozen=True):
    """OKX Signal Bot configuration."""

    signal_token: str = ""
    instrument_format: str = "okx"  # "okx" or "tradingview"
    max_lag: int = 60  # seconds


class SignalDefaultsConfig(msgspec.Struct, frozen=True):
    """Default values for signals when not specified."""

    order_type: str = "market"  # "market" or "limit"
    order_price_offset: float = 0.1  # percentage for limit orders
    investment_type: str = "percentage_investment"


class SignalConfig(msgspec.Struct, frozen=True):
    """Signal processing configuration."""

    okx: OkxConfig = OkxConfig()
    defaults: SignalDefaultsConfig = SignalDefaultsConfig()
    raw: dict | None = None


def build_signal_config(signal_dict: dict | None, raw_dict: dict | None = None) -> SignalConfig:
    """
    Build SignalConfig from dictionary.

    Args:
        signal_dict: Dictionary with signal configuration

    Returns:
        SignalConfig instance
    """
    if signal_dict is None:
        return SignalConfig()

    # Build OKX config
    okx_dict = signal_dict.get("okx", {})
    okx_config = OkxConfig(
        signal_token=okx_dict.get("signal_token", ""),
        instrument_format=okx_dict.get("instrument_format", "okx"),
        max_lag=okx_dict.get("max_lag", 60),
    )

    # Build defaults config
    defaults_dict = signal_dict.get("defaults", {})
    defaults_config = SignalDefaultsConfig(
        order_type=defaults_dict.get("order_type", "market"),
        order_price_offset=defaults_dict.get("order_price_offset", 0.1),
        investment_type=defaults_dict.get("investment_type", "percentage_investment"),
    )

    return SignalConfig(
        okx=okx_config,
        defaults=defaults_config,
        raw=raw_dict,
    )
