# Athanor engine (not yet implemented)

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
