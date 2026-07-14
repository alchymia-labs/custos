# Custos

**Custos** (Latin: *guardian*) is the non-custodial, self-hosted execution
runner of [The Alephain Guild](https://github.com/the-alephain-guild)
ecosystem. It is the daemon an operator installs on their own infrastructure
to run backtested NautilusTrader strategies against live venues — holding
their own API keys in a local vault, never surrendering them to any cloud
product. Custos consumes authorized immutable deployment intent backed by
**Crucible Rust**, while **ARX** supplies identity/RBAC assertions. It reports
signed execution, venue and fee facts keyed to the exact deployment instance.

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

- **Keys and strategy logic never leave the operator's machine.** Data leaving
  Custos is limited to signed whitelisted RunnerFacts: execution telemetry,
  status, reconciliation evidence, exact venue fee/funding facts, and strictly
  redacted `RunnerRuntimeLogFact.v1` records. Custos never forwards stdout.
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
| **enrollment** | Nonce-bound Ed25519 PoP; encrypted machine credential; rotate/revoke/fail-closed startup | [docs/design/enrollment.md](docs/design/enrollment.md) |
| **reconcile** | Declarative loop: pull `DeploymentSpec` → start/stop NT → report `DeploymentStatus` | [docs/design/reconcile.md](docs/design/reconcile.md) |
| **nautilus_host** | NautilusTrader process supervision + `ExecutionEngineAdapter` (CEX/NT) + G6 host gate | [docs/design/nautilus_host.md](docs/design/nautilus_host.md) |
| **telemetry_actor** | NT MessageBus → whitelisted, buffered NATS uplink with schema versioning | [docs/design/telemetry_actor.md](docs/design/telemetry_actor.md) |
| **credential_vault** | sops+age exchange-key and machine-principal vault; KEK never leaves the box | [docs/design/credential_vault.md](docs/design/credential_vault.md) |
| **nats_client** | NATS JetStream client + transport envelope schema + subject naming | [docs/design/nats_client.md](docs/design/nats_client.md) |

The domain vocabulary shared across these modules is described in
[docs/domain.md](docs/domain.md).

## Supported Trading Modes

`spec.trading_mode` selects the venue path, while `--engine` selects the local
execution host. The 0.3.0 default is `--engine nautilus`, which starts the real
NautilusTrader host. `--engine noop` is an explicit contract-test stub and can
never clear the live G6 gate.

| Mode | Execution | Status | Notes |
|------|-----------|--------|-------|
| `sandbox` | Real-time Binance data, locally simulated fills (no exchange contact) | ✅ | Seed balances via `sandbox.starting_balances`. |
| `testnet` | Real Binance exec against the testnet endpoint (test funds) | ✅ | See [examples/supertrend-testnet](examples/supertrend-testnet/). |
| `live` | Real Binance exec against the live exchange | ⚠️ | Must clear the 4-layer G6 gate (host capability, venue, `code_hash`, credential scope) **and** carry cloud-side dual approval (`>= 2` distinct `approved_by`). Per-order telemetry is not uplinked to arx until the telemetry bridge lands (see Not Included Yet). |

The verified local 0.3.0 image contains NautilusTrader, PyYAML, sops, and age.
It is the current downstream-development runtime for sandbox, testnet, and
live; downstream projects do not need to extend it just to obtain runtime
dependencies.

## Quick Start

Build and gate the complete local runtime, then confirm the clean entrypoint:

```bash
make verify-local-v030
docker run --rm custos-runner:v0.3.0 --help
```

**Remote release: deferred.** No 0.3.0 Git tag, GitHub Release, PyPI artifact,
or GHCR image is asserted as published by this repository state.

For a standalone NATS deployment, bootstrap topology explicitly before the
runner starts:

```bash
docker run --rm --network host \
  custos-runner:v0.3.0 \
  nats bootstrap --profile standalone --nats-url nats://127.0.0.1:4222 \
  --tenant-id acme

docker run --rm --network host \
  -v "$HOME/.arx:/home/custos/.arx" \
  -e SOPS_AGE_KEY_FILE=/home/custos/.arx/age.key \
  custos-runner:v0.3.0 \
  start --nats-url nats://127.0.0.1:4222 \
  --reconcile-strategy-id supertrend-btcusdt --engine nautilus
```

Enrollment and per-key vault provisioning happen before `start`; see the
[deployment runbook](docs/ops/05-deployment.md) and the runnable
[testnet Compose example](examples/supertrend-testnet/).

Startup is fail closed: the local machine credential must be present,
unexpired, exactly bound to `runner.toml`, active at the Crucible authority,
and backed by the same validated capability key used for RunnerFacts.

Source development uses `uv sync --extra dev --extra nautilus`. The dev-only
base contract intentionally remains lightweight and is verified separately by
`make verify-base-clean`.

## 0.3.0 Clean Deployment Contract

The runtime accepts only the strict `custos.contracts.DeploymentSpec` shape.
Producers publish a `DeploymentMessage` through `arx-runner deployment publish`;
standalone operators create streams through `arx-runner nats bootstrap`; probes
use `arx-runner health`. Lifecycle and trading mode are separate: `generation`
starts at 1 and `lifecycle_state` is `running`, `paused`, `stopped`, or
`archived`.

The downstream migration gate is explicit:

```text
PS Plan 49 must not execute against custos < 0.3.0.
PS must consume the verified local image directly.
PS must not maintain a derived custos Dockerfile.
PS owns strategy_config assembly only.
```

## Upgrade from 0.1.x (Breaking Change — 0.2.0)

Version 0.2.0 introduces a clean-break CLI redesign aligned with arx
`docs/team-self-hosted-lifecycle.md` Phase 0.2 + 0.3. Existing operators
must run through the following steps once:

1. `pip install --upgrade custos-runner` (or `uv sync --extra dev`).
2. The `python -m custos ...` / `custos ...` entry points are **removed**
   — they now exit code 2 with a pointer to `arx-runner start`. Use the
   subcommand dispatcher instead.
3. Do not migrate old `enrollment.json`, plaintext `long_term_credential`, or
   `runner-fact-key.json` files. Remove them and re-enroll into the v2
   sops+age machine vault; no compatibility reader exists.
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

- Custos uses ARX public typed HTTP URLs for enrollment, credential lifecycle,
  and authorized control calls. ARX supplies access control but owns no Runner
  business state.
- Signed RunnerFacts publish to the canonical Crucible JetStream subject;
  Crucible verifies the machine key, exact deployment/capability binding,
  sequence, and deduplication before append-only projection.
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

Most of the original 0.1.x follow-ups shipped in 0.2.0. The distribution +
release-engineering + LTS-policy items are documented in
[`CHANGELOG.md`](CHANGELOG.md) and [`docs/lts-commitment.md`](docs/lts-commitment.md);
public-repo façade lives in [`CONTRIBUTING.md`](CONTRIBUTING.md) +
[`SECURITY.md`](SECURITY.md).

The remaining follow-ups tracked here:

- **Remote 0.3.0 publication** — deferred until a dedicated release plan
  decides the GitHub repository and GHCR namespace, the cosign identity and
  tag ownership, and the PyPI trusted publisher identity, then promotes one
  digest-tested artifact without rebuilding it.
- **1.0.0 promote** — requires three consecutive compatible minor releases,
  completed machine-credential v2 rollout, and gateway-contract coverage.
