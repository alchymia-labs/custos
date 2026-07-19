---
title: "NautilusTrader Engine"
sidebar_position: 1
---

<!-- source: docs/engines/nautilus.md -->

# NautilusTrader Engine

:::warning 🔄 中文翻译进行中 · PLAN 20 T6
本章中文正文将在 Plan 20 T6 完成。当前显示英文占位。
:::

> Status: **implemented** (`src/custos/engines/nautilus/`). This page is an
> overview and index — the full design (process lifecycle, G6 gate, venue
> adapters) lives in [`docs/design/nautilus_host.md`](../design/nautilus_host.md)
> and is not duplicated here.

## What it is

[NautilusTrader](https://github.com/nautechsystems/nautilus_trader) is an
event-driven, Python-native algorithmic trading platform with a Rust core.
It is Custos's reference execution engine: the six core modules (reconcile,
telemetry_actor, credential_vault, etc.) were designed and validated against
it first, and every other engine in this directory is a future integration
that follows the same `ExecutionEngineProtocol` contract NautilusTrader
already satisfies.

## Relationship to `ExecutionEngineProtocol`

`src/custos/engines/nautilus/host.py` provides two implementations:

- `NoopHost` — a stub that never touches a real venue; used for paper / dev
  runs and as the fail-safe target when the G6 gate denies a live deploy.
- `NtTradingNodeHost` — the real implementation, supervising a NautilusTrader
  `TradingNode` process across `sandbox` / `testnet` / `live` trading modes.

Both satisfy the Tier-1 contract in
[`docs/design/engine_protocol.md`](../design/engine_protocol.md); the mapping
from each Tier-1 method to the underlying NT SDK call is documented in
[`docs/design/nautilus_host.md`](../design/nautilus_host.md).

## Where to look next

| Topic | Doc |
|-------|-----|
| Process lifecycle, G6 gate, venue adapters | [`docs/design/nautilus_host.md`](../design/nautilus_host.md) |
| `ExecutionEngineProtocol` Tier-1/Tier-2 contract | [`docs/design/engine_protocol.md`](../design/engine_protocol.md) |
| Strategy loading (vendored toolkit) | `src/custos/engines/nautilus/strategy_loader.py` |
| Binance venue adapter | `src/custos/engines/nautilus/venue_binance.py` |
| Optional dependency | `pyproject.toml` → `[project.optional-dependencies].nautilus` |

## Follow-up plans

Strategy migrations onto this engine (e.g. the Supertrend strategy) and the
vendored indicator toolkit under `src/custos/engines/nautilus/toolkit/` are
tracked by their own plans, not this stub.
