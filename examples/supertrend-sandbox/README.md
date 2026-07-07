# Sandbox deployment example — `NtTradingNodeHost`

Runs a NautilusTrader strategy through the custos governance surface (vault +
reconcile + NATS) in **sandbox mode**: a real-time Binance data feed with a
locally simulated execution venue, so orders are filled against live prices
without ever reaching the exchange. No real funds, no live credentials required
for fills.

## Prerequisites

The NautilusTrader host runtime is an optional extra and needs Python 3.12+:

```bash
uv sync --extra dev --extra nt-runtime   # or: pip install "custos-runner[nt-runtime]"
```

A base install (audit / paper mode, `NoopHost`) does not pull NautilusTrader and
runs on Python 3.11+.

## The DeploymentSpec

[`spec-example.json`](./spec-example.json) is the spec the cloud (arx) hands to
the runner over NATS. The reconcile loop applies it and calls
`NtTradingNodeHost.deploy(spec, credential)`.

| Field | Meaning |
|-------|---------|
| `trading_mode` | `sandbox` — real data, simulated fills. `live` is still blocked by the G6 gate. |
| `strategy_path` | Absolute path to the strategy source on the runner host. |
| `code_hash` | sha256 of the strategy directory. `null` skips the check (sandbox only, audited); live must pin it. |
| `connector` | `binance_perpetual` (USDT futures) or `binance` (spot). Other venues are rejected. |
| `pairs` | Trading pairs; `leverage` pins per-instrument leverage for futures. |
| `sandbox.starting_balances` | Simulated account seed balances. |
| `provenance_ref.credential_id` | Vault reference; the runner decrypts it locally — the raw key never leaves the process. |

## Credential

The runner never receives raw keys over the wire. `credential_id` is resolved by
the local `credential_vault` (sops + age), which returns:

```json
{
  "api_key": "<local only>",
  "api_secret": "<local only>",
  "permission_scope": "trade_no_withdraw"
}
```

The vault rejects any credential whose scope is not `trade_no_withdraw`.

## What deploy does

1. Verifies `code_hash` against the on-disk strategy (skipped + audited when `null`).
2. Builds the Binance data-client config and the sandbox execution-client config.
3. Assembles a `TradingNode`, registers the strategy, and runs it in a background
   task so the reconcile loop is never blocked.
4. `stop` tears the node down gracefully with a bounded timeout.

Live / testnet promotion and the NT MessageBus → telemetry bridge are follow-up
plans; until then live deployments stay blocked by the G6 gate.
