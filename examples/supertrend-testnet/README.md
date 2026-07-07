# Example: SuperTrend on Binance testnet

Run a reviewed NautilusTrader strategy against the **Binance testnet** through a
custos runner, driven by a `DeploymentSpec` with `trading_mode: testnet`. It
exercises the full local path — reconcile loop → G6 host gate → real
`NtTradingNodeHost` → Binance testnet exec client — with test funds, no real
money at risk.

> **Observability is partial in this example.** The Plan 00b telemetry bridge
> (NT `MessageBus` → arx) has not landed yet, so `OrderDenied` / fill events are
> **not** uplinked to the cloud (arx). A real testnet run here is observable only
> through custos's **local `structlog` output** (`docker compose logs runner`).
> Heartbeat and reconcile status still reach NATS; per-order execution telemetry
> does not, until Plan 00b.

## What it is (and is not)

- **Is:** a runnable scaffold — a compose stack, a `DeploymentSpec`, a
  sops+age vault template, and the exact commands to wire them together.
- **Is not:** a bundled strategy or bundled keys. You provide your own reviewed
  strategy and your own Binance **testnet** API keys.

## Prerequisites

- Docker + Docker Compose v2 (`docker compose`, not `docker-compose`).
- A Binance **testnet** account and API key/secret
  (<https://testnet.binancefuture.com> for USDT-perpetual). The key must be
  **trade-only, no withdrawal** — custos refuses any other scope.
- [`age`](https://github.com/FiloSottile/age) and
  [`sops`](https://github.com/getsops/sops) on your host to encrypt the
  credentials (they are also installed inside the runner image, which decrypts
  at runtime).

## Why credentials go through sops+age, not `.env`

custos is **non-custodial**: exchange keys and the key-encryption key never
leave the machine you run on. So this example puts keys in a **sops+age
encrypted file** decrypted locally by the runner — not in `.env` (which would be
plaintext). `.env` here holds only non-secret runtime config (tenant/runner/NATS
ids). The `age` private key is mounted **read-only** and never baked into the
image or sent anywhere.

## Steps

### 1. Runtime config

```bash
# Do NOT overwrite a .env you are already using.
[ -f .env ] || cp .env.example .env
# Edit .env if your ids differ from the defaults.
```

### 2. Your strategy

Put your reviewed / backtested strategy at `./strategy/strategy.py` (mounted
read-only to `/app/strategy/strategy.py`, which `spec-example.json` points at).
It must be a `nautilus_trader.trading.strategy.Strategy` subclass whose class
name ends in `Strategy`, or expose `STRATEGY_CLASS` / a `create_strategy(config)`
factory.

```bash
mkdir -p strategy
cp /path/to/your/supertrend/strategy.py strategy/strategy.py
```

### 3. Encrypt your testnet credentials

```bash
# One-time: generate an age keypair. Keep the private key local.
mkdir -p vault
age-keygen -o vault/age.key
# Note the "Public key: age1..." line it prints.

# Fill in your real testnet keys, then encrypt.
cp vault-fixture/credentials.example.json vault/credentials.plain.json
$EDITOR vault/credentials.plain.json        # set api_key / api_secret

sops --encrypt --age <age1-public-key-from-above> \
    vault/credentials.plain.json > vault/credentials.enc.json
rm vault/credentials.plain.json             # keep only the encrypted copy
```

The decrypted structure is a map keyed by `credential_id` (here
`binance-testnet`, matching `spec-example.json`'s `provenance_ref.credential_id`), each
entry carrying `api_key` / `api_secret` / `key_type` / `permission_scope`.
`permission_scope` must be `trade_no_withdraw` or the runner refuses it.

> `vault/`, `.env`, and `*.plain.json` are all git-ignored — never commit them.

### 4. Start the stack

```bash
docker compose up --build
```

The runner connects to NATS, starts the reconcile loop for `ARX_STRATEGY_ID`,
and publishes heartbeats. It is now waiting for a `DeploymentSpec`.

### 5. Publish the DeploymentSpec

Normally **arx** publishes the spec. For a standalone test, publish
`spec-example.json` (as the `payload` of a transport envelope) to the JetStream
subject `arx.<tenant>.deployment_spec.<strategy_id>` — for the defaults,
`arx.acme.deployment_spec.supertrend-btcusdt`. The stream is level-triggered by
`generation`: each message is a full snapshot, so bump `generation` to redeploy.

`spec-example.json` sets `code_hash: null`: the G6 gate pins `code_hash` only
for `live` mode, and for `testnet` the strategy loader records a
`code_hash_skipped` audit event and proceeds. A `live` spec **must** carry a
matching `code_hash` and, on the arx side, `>= 2` distinct `approved_by` entries.

### 6. Observe

```bash
docker compose logs -f runner
```

Look for `nt_deploy_started` (with `trading_mode=testnet`), then order/fill
events in the NautilusTrader logs. Remember: these are **local only** until the
Plan 00b telemetry bridge lands (see the note at the top).

## Manual smoke test

There is no automated end-to-end test against Binance testnet — CI has no
secrets. To smoke-test by hand:

1. Complete steps 1–5 above with real testnet keys.
2. Confirm `nt_deploy_started` appears in `docker compose logs runner`.
3. Watch for the strategy submitting orders and Binance testnet acknowledging
   fills in the logs.
4. Publish a spec with `lifecycle_state: stopped` (and a higher `generation`) to
   tear the deployment down; confirm `nt_stop_completed`.

## Going to production (live)

- Keep credentials in sops+age; never place keys in `.env` or the image.
- Store the `age` private key with `0600` permissions on the runner host only.
- A `live` deploy additionally requires a pinned `code_hash` and cloud-side dual
  approval (`approved_by`); the G6 gate refuses a live deploy that is missing
  either.
