from decimal import Decimal

from custos.engines.nautilus.risk import PreTradeRuleConfig, build_nt_risk_engine_config


def test_risk_policy_compiles_to_pure_local_decimal_config() -> None:
    rule = PreTradeRuleConfig(
        rule_id="rule-1", strategy_id=None, symbol="BTC-USDT",
        max_qty=Decimal("1"), max_notional=Decimal("1000"),
        notional_ccy="USDT", price_collar_bps=50, dedup_window_ms=1000,
    )
    config = build_nt_risk_engine_config([rule])
    assert config["max_notionals_per_order"] == {"BTC-USDT": "1000"}
    assert config["local_pre_trade"][0]["max_qty"] == "1"
