# Freqtrade engine (not yet implemented)

> Status: **future candidate**. No code exists under
> `src/custos/engines/freqtrade/` yet; `pyproject.toml` reserves an empty
> `freqtrade` optional-dependency slot for it.

## What it is

[Freqtrade](https://github.com/freqtrade/freqtrade) is an open-source
Python crypto trading bot with a built-in backtesting engine, hyperopt
parameter tuner, and a strategy interface based on pandas DataFrames.

## Similarity to NautilusTrader

- Python-native, no subprocess/IPC bridge needed.
- Has its own exchange connector abstraction (built on `ccxt`) that a
  `FreqtradeHost` would wrap, the same way `NtTradingNodeHost` wraps NT's
  `TradingNode`.
- Like NautilusTrader, ships its own backtesting engine — a Freqtrade
  integration could in principle share Custos's declarative `DeploymentSpec`
  → reconcile → telemetry pipeline unchanged.

## Difference from NautilusTrader

- Freqtrade's strategy interface is DataFrame/indicator-driven (`populate_indicators`
  / `populate_entry_trend` / `populate_exit_trend`), a different programming
  model from NT's event-driven `Strategy` subclass with `on_bar`/`on_trade`
  handlers. Strategies are not portable across the two without a rewrite.
- Freqtrade instances are typically run as a REST-API-fronted process
  (FreqUI / freqtrade-client), which may need adapting to fit Custos's
  fully-local, non-custodial supervision model (no exposed REST surface,
  per the ecosystem's single-exit rule — see `docs/domain.md`).

## Onboarding path

Follow the 5-step template in
[`docs/design/engine_protocol.md`](../design/engine_protocol.md#engine-onboarding-template-5-steps):
implement `ExecutionEngineProtocol` in a new `custos/engines/freqtrade/host.py`,
fill the (currently empty) `freqtrade` extra in `pyproject.toml`, and add
venue adapters as needed.

## Follow-up plan

Not yet scheduled. A dedicated plan should scope the Freqtrade integration
when there is concrete demand for indicator-driven strategies on Custos.
