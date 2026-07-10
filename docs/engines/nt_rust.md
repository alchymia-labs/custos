# NautilusTrader Rust core engine (not yet implemented)

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
