# Hummingbot engine (not yet implemented)

> Status: **future candidate**. No code exists under
> `src/custos/engines/hummingbot/` yet; `pyproject.toml` reserves an empty
> `hummingbot` optional-dependency slot for it.

## What it is

[Hummingbot](https://github.com/hummingbot/hummingbot) is an open-source
Python framework for market-making and liquidity-provision strategies
across centralized and decentralized exchanges. Where NautilusTrader is
built around a general event-driven backtest/live engine, Hummingbot is
purpose-built around market-making connector strategies (pure market
making, cross-exchange, AMM arbitrage, etc.).

## Similarity to NautilusTrader

- Python-native, async execution model — compatible with Custos's asyncio
  daemon architecture (no subprocess/IPC bridge needed, unlike the Rust
  engines below).
- Has its own venue connector abstraction, analogous to NautilusTrader's
  `ExecutionClient` — a `HummingbotHost` would wrap Hummingbot's connector
  layer the way `NtTradingNodeHost` wraps NT's `TradingNode`.

## Difference from NautilusTrader

- Hummingbot's process model is a standalone bot instance with its own
  config/strategy file conventions, not a library you embed the way NT's
  `TradingNode` is embedded in `nautilus_host.py`. Supervising a Hummingbot
  instance may look more like process supervision (spawn + monitor) than
  the current in-process `TradingNode` construction.
- Strategy authoring conventions differ significantly (Hummingbot strategies
  are not directly portable from NT `Strategy` subclasses).

## Onboarding path

Follow the 5-step template in
[`docs/design/engine_protocol.md`](../design/engine_protocol.md#engine-onboarding-template-5-steps):
implement `ExecutionEngineProtocol` in a new `custos/engines/hummingbot/host.py`,
fill the (currently empty) `hummingbot` extra in `pyproject.toml`, and add
venue adapters as needed. The command coordinator and admission rules require
no engine-specific branch; they operate through `ExecutionEngineProtocol` and
the verified artifact ABI.

## Follow-up plan

Not yet scheduled. A dedicated plan should scope the Hummingbot integration
when there is concrete demand for market-making strategies on Custos.
