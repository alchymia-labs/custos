# Custos

**Custos** (Latin: *guardian*) is the non-custodial, self-hosted execution
runner of [The Alephain Guild](https://github.com/the-alephain-guild)
ecosystem. It is the daemon an operator installs on their own infrastructure
to run backtested NautilusTrader strategies against live venues — holding
their own API keys in a local vault, never surrendering them to any cloud
product. Custos pairs with **arx** (the ecosystem's coordination gateway),
pulling its desired deployment state and phoning execution telemetry home.

## Why Public Open Source

Custos is Apache-2.0 and public from day one. This is not incidental — it is
the *verifiable fulfillment* of the ecosystem's **non-custodial** red line.
The runner holds the operator's venue keys and executes real trades on their
infrastructure; an operator can only rationally trust such a daemon if they
can read exactly what it does with those keys. Open source turns "Key and
strategy logic stay local" from a design claim into an engineering fact the
operator can audit line by line. (See
[ADR-012 v4 §Custos](https://github.com/the-alephain-guild) and
[ADR-014 v6 §Non-Custodial Trust Model].)

## Trust Boundary

The trust boundary of the whole ecosystem is *the Custos line*:

- **Keys and strategy logic never leave the operator's machine.** The only
  data leaving Custos is execution telemetry and status reports.
- **Control is declarative, not imperative.** Custos *pulls* the desired
  deployment state and reconciles the local NautilusTrader process to match
  it — the product plane writes desired state, it never `docker run`s into
  the operator's box. This declarative reconciliation is what makes Custos a
  genuine self-hosted runner rather than a remote-controlled agent.
- **Cloud outage degrades gracefully.** Organization-level cross-account
  circuit-breaking is aggregated in the cloud when reachable, but each runner
  retains a local fallback breaker (per-strategy / per-account drawdown) plus
  a structural `max_notional_per_runner` cap. A cloud outage never stops
  local trading or removes local protection.

## Modules (六件套)

Custos is organized as six core modules, each documented under `docs/`:

| Module | Responsibility | Design doc |
|--------|----------------|------------|
| **enrollment** | One-time EnrollmentToken pairing; `runner_id` persistence; `paper_only` default | [docs/enrollment.md](docs/enrollment.md) |
| **reconcile** | Declarative loop: pull `DeploymentSpec` → start/stop NT → report `DeploymentStatus` | [docs/reconcile.md](docs/reconcile.md) |
| **nautilus_host** | NautilusTrader process supervision + `ExecutionEngineAdapter` (CEX/NT) + G6 host gate | [docs/nautilus_host.md](docs/nautilus_host.md) |
| **telemetry_actor** | NT MessageBus → whitelisted, buffered NATS uplink with schema versioning | [docs/telemetry_actor.md](docs/telemetry_actor.md) |
| **credential_vault** | sops+age local key vault; KEK never leaves the box; `trade_no_withdraw` scope | [docs/credential_vault.md](docs/credential_vault.md) |
| **nats_client** | NATS JetStream client + transport envelope schema + subject naming | [docs/nats_client.md](docs/nats_client.md) |

The domain vocabulary shared across these modules is described in
[docs/domain.md](docs/domain.md).

## Supported Trading Modes

`spec.trading_mode` selects the execution path. The G6 host gate guards the live
transition; paper / dev runs use the `NoopHost` stub (default), while
`--use-nt-host` selects the real NautilusTrader host needed for sandbox / testnet
/ live.

| Mode | Execution | Status | Notes |
|------|-----------|--------|-------|
| `sandbox` | Real-time Binance data, locally simulated fills (no exchange contact) | ✅ | Seed balances via `sandbox.starting_balances`. |
| `testnet` | Real Binance exec against the testnet endpoint (test funds) | ✅ | See [examples/supertrend-testnet](examples/supertrend-testnet/). |
| `live` | Real Binance exec against the live exchange | ⚠️ | Must clear the 4-layer G6 gate (host capability, venue, `code_hash`, credential scope) **and** carry cloud-side dual approval (`>= 2` distinct `approved_by`). Per-order telemetry is not uplinked to arx until the telemetry bridge lands (see Not Included Yet). |

> All three real-execution modes require `--use-nt-host` to select the real
> `NtTradingNodeHost`. Without it the runner uses the `NoopHost` stub (paper /
> dev only); a `live` spec on the stub is refused by the G6 gate, and a
> `sandbox` / `testnet` spec on the stub is a no-op (no real NT node starts).

## Quick Start

```bash
uv sync --extra dev

# 1. Pair the runner with the backend (writes ~/.arx/runner.toml at 0600).
arx-runner enroll --token <ONE-SHOT-TOKEN> --backend http://team-server:8000 \
    --tenant-id acme --runner-id runner-7

# 2. Provision exchange credentials (one .enc per key-id, sops+age encrypted).
export SOPS_AGE_RECIPIENT=age1...
export MY_API_SECRET=...
arx-runner vault put --key-id binance-paper --tenant-id acme \
    --api-key <PUBLIC-KEY> --api-secret-env MY_API_SECRET

# 3. Start the reconcile / telemetry / heartbeat loop.
arx-runner start
```

## Upgrade from 0.1.x (Breaking Change — 0.2.0)

Version 0.2.0 introduces a clean-break CLI redesign aligned with arx
`docs/team-self-hosted-lifecycle.md` Phase 0.2 + 0.3. Existing operators
must run through the following steps once:

1. `pip install --upgrade custos-runner` (or `uv sync --extra dev`).
2. The `python -m custos ...` / `custos ...` entry points are **removed**
   — they now exit code 2 with a pointer to `arx-runner start`. Use the
   subcommand dispatcher instead.
3. Move persisted state from `~/.custos/` to `~/.arx/`:
   ```bash
   mv ~/.custos/enrollment.json ~/.arx/enrollment.json
   mv ~/.custos/state ~/.arx/state
   # (assumes bash / zsh; on POSIX `sh` run the two mv statements verbatim)
   ```
4. The legacy `SopsAgeVault` multi-credential-in-one-JSON sops file is
   removed. Decrypt any old vault manually with `sops --decrypt <path>`
   and re-add each key via `arx-runner vault put` (per-key `.enc` model).
5. The `--sops-file` / `--age-key-file` flags are gone. `arx-runner start`
   now reads `~/.arx/vault/<key-id>.enc` files directly through
   `PerKeyVault`.

No auto-migration command is provided (CEO clean-break directive
2026-07-10). The one-time operator cost avoids long-term dual-CLI /
dual-namespace drift.

## Contract with Arx (Gateway)

Custos does **not** expose any API directly to end users, API clients, or
dashboards. Its direct counterparty is **arx**, the coordination gateway:

- Custos reports `heartbeat` / execution telemetry / reconcile status to arx
  over NATS/HTTP, and pulls its `DeploymentSpec` from arx.
- arx, in turn, aligns with **Crucible** (the ecosystem's production
  execution-of-record) on the operator's behalf. Custos never talks to
  Crucible directly — arx mediates.
- The contract is maintained as a versioned API (OpenAPI / JSON Schema)
  against arx's `ExecutionEngineAdapter` protocol.

**Single external exit:** arx is the *only* external entry point to the
ecosystem and the access-control layer for it. Any external access to Custos
state must pass arx's tenancy `gatekeeper` and be mediated by arx's
coordination `CustosGateway` inbound handler. Custos itself is never exposed
to external clients.

## License & Versioning

- **License:** Apache-2.0 (see [LICENSE](LICENSE) and [NOTICE](NOTICE)).
- **Versioning:** strict [SemVer](https://semver.org/) with a long-term
  support window (EOL ≥ 12 months per release line).

## Not Included Yet

The following are deliberately out of scope for the initial extraction and
tracked as follow-ups:

- **CI + signed release pipeline** — signed wheel + signed docker image
  (`ghcr.io/...`) + reproducible build (ADR-012 v4 stage-3 action items).
- **Contract versioning mechanism** — custos ↔ arx OpenAPI/JSON Schema
  registry + SemVer tagging.
- **`CONTRIBUTING.md` + `SECURITY.md`** — public-repo façade completion.
- **Python package rename** — completed (Plan 05, `arx_runner` → `custos`).
- **Telemetry uplink bridge** — the NT `MessageBus` → arx telemetry actor is not
  wired yet, so per-order execution events (fills / `OrderDenied`) are observable
  only in the runner's local logs, not uplinked to the cloud.
