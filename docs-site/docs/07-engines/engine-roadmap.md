---
title: "Engine Roadmap"
sidebar_position: 3
---

<!-- source: docs/engines/hummingbot.md + docs/engines/freqtrade.md + docs/engines/athanor.md + docs/engines/nt_rust.md -->

# Engine Roadmap

This chapter provides an index of engine adapters planned or supported by custos beyond the default Nautilus Trader engine (see [nautilus-trader](./nautilus-trader)).

## hummingbot

<!-- source: docs/engines/hummingbot.md -->

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
venue adapters as needed. The G6 gate and reconciler require no changes —
they already operate exclusively through `ExecutionEngineProtocol`.

## Follow-up plan

Not yet scheduled. A dedicated plan should scope the Hummingbot integration
when there is concrete demand for market-making strategies on Custos.

## freqtrade

<!-- source: docs/engines/freqtrade.md -->

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

## athanor

<!-- source: docs/engines/athanor.md -->

> Status: **future candidate**. No code exists under
> `src/custos/engines/athanor/` yet; `pyproject.toml` reserves an empty
> `athanor` optional-dependency slot for it.

## What it is

Athanor is the Alephain Guild's MEV research and execution engine, written
in Rust. Unlike the other engines in this directory it is not a Python
library — integrating it means bridging across a language boundary.

## Similarity to NautilusTrader

- Same contract-level relationship to Custos: an `AthanorHost` would still
  need to satisfy `ExecutionEngineProtocol`'s Tier-1 `deploy` / `reconfigure`
  / `stop` / `supports_live` / `supports_venue` methods, whatever runs
  underneath. The reconciler and G6 gate do not care what language the
  engine is implemented in — they only see the Protocol.

## Difference from NautilusTrader — Rust IPC / subprocess bridge

This is the key architectural difference from every other engine in this
directory: Athanor is a separate Rust binary/process, not something that
can be `import`ed into the asyncio daemon. A Custos integration would need
one of:

- **Subprocess supervision** — spawn the Athanor binary as a child process
  (similar in spirit to how `NtTradingNodeHost` supervises the NT
  `TradingNode`, but across a process boundary rather than in-process), and
  communicate over stdin/stdout, a local Unix socket, or a local gRPC
  endpoint.
- **FFI bridge** — a Python extension module (e.g. via `pyo3`) exposing a
  synchronous or async-compatible interface to an embedded Athanor core.

Either approach must preserve the non-custodial red lines: credentials
still originate from `credential_vault` and must never cross the process
boundary as environment variables or command-line arguments in a way that
leaks them to logs or process listings (see `mandatory-rules.md` §0.1).

## Onboarding path

Follow the 5-step template in
[`docs/design/engine_protocol.md`](../design/engine_protocol.md#engine-onboarding-template-5-steps),
with an additional design step (0): decide and document the subprocess/IPC
or FFI bridge mechanism before implementing `ExecutionEngineProtocol` in
`custos/engines/athanor/host.py`, since that decision shapes the whole
integration.

## Follow-up plan

Not yet scheduled. A dedicated plan should scope the Athanor integration,
including the IPC/FFI bridge design, when there is concrete demand for
MEV-related execution on Custos.

## nt_rust

<!-- source: docs/engines/nt_rust.md -->

> Status: **future candidate**. No code exists under
> `src/custos/engines/nt_rust/` yet; `pyproject.toml` reserves an empty
> `nt-rust` optional-dependency slot for it.

## What it is

NautilusTrader's execution core is progressively migrating from Python to
Rust for performance-sensitive paths (order book, matching engine, message
bus). This stub tracks a possible *second*, Rust-native integration with
that core — distinct from `custos/engines/nautilus/`, which wraps NT's
Python SDK (`nautilus_trader` package, itself Rust-backed but consumed
through its Python API).

## Similarity to the existing `nautilus` engine

- Same underlying execution semantics and venue connectors as
  `docs/engines/nautilus.md` — this is not a different trading engine, it
  is a different **binding** to the same one, so most of the design
  knowledge in [`docs/design/nautilus_host.md`](../design/nautilus_host.md)
  (G6 gate mapping, trading-mode dispatch) carries over conceptually.
- Same `ExecutionEngineProtocol` contract requirement as every other engine.

## Difference from the existing `nautilus` engine — Rust IPC / subprocess bridge

The distinguishing question this integration would answer is: *is calling
into NT's Rust core directly (bypassing the Python SDK layer) worth the
added complexity?* If so, the bridge options mirror Athanor's
(see [`docs/engines/athanor.md`](athanor.md)):

- **FFI bridge** — `pyo3`-based Python extension calling the Rust core
  in-process, keeping Custos's single-process asyncio model intact.
- **Subprocess / IPC** — a standalone Rust process supervised the way
  `NtTradingNodeHost` supervises the Python `TradingNode`, communicating
  over a local socket.

Either approach only makes sense if profiling shows the existing
`custos/engines/nautilus/` (Python SDK) path is a bottleneck for a real
workload — this is a performance-motivated integration, not a
feature-motivated one, unlike Hummingbot/Freqtrade/Athanor.

## Onboarding path

Follow the 5-step template in
[`docs/design/engine_protocol.md`](../design/engine_protocol.md#engine-onboarding-template-5-steps),
with the same additional bridge-design step called out in
[`docs/engines/athanor.md`](athanor.md#onboarding-path).

## Follow-up plan

Not yet scheduled. Only worth scoping once the existing Python `nautilus`
engine has a measured performance ceiling that a Rust-core binding would
actually raise.
