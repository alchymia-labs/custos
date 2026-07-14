# SuperTrend on Binance testnet with Custos 0.3.0

This Compose example runs only the Custos execution boundary from the verified
local `custos-runner:v0.3.0` image. A reachable Crucible deployment service and
its provisioned JetStream domain-event stream are prerequisites. No derived
Custos Dockerfile, local business-stream bootstrap, or runner-side command
publisher is used.

## Prerequisites

- Docker with Compose v2.
- A reviewed strategy at `strategy/strategy.py`.
- Crucible HTTP and NATS endpoints plus its domain-event public key.
- A one-time runner enrollment token.
- Binance testnet credentials with withdrawal disabled.

Build and verify the exact local image:

```bash
make verify-local-v030
cd examples/supertrend-testnet
test -f .env || cp .env.example .env
set -a; . ./.env; set +a
```

## 1. Enroll the machine principal

```bash
mkdir -p runtime/.arx/vault runtime/.arx/state
chmod 700 runtime/.arx runtime/.arx/vault runtime/.arx/state
age-keygen -o runtime/.arx/age.key
chmod 600 runtime/.arx/age.key
export SOPS_AGE_RECIPIENT="$(age-keygen -y runtime/.arx/age.key)"

docker run --rm \
  -v "$PWD/runtime/.arx:/home/custos/.arx" \
  -e SOPS_AGE_RECIPIENT \
  custos-runner:v0.3.0 enroll \
  --token '<one-time-token>' \
  --backend "$CRUCIBLE_HTTP_URL" \
  --tenant-id "$CUSTOS_TENANT_ID" \
  --runner-id "$CUSTOS_RUNNER_ID"
```

The `arx-runner enroll` flow creates `runner.toml` public metadata and an
encrypted runner machine credential. Do not construct either file manually.
Install the Crucible event verification key at
`runtime/.arx/crucible-domain-event.pub`.

## 2. Provision the venue credential

The container entrypoint below invokes the same `arx-runner vault put` command
used by a source installation.

```bash
printf '%s\n' '<binance-testnet-api-secret>' | docker run --rm -i \
  -v "$PWD/runtime/.arx:/home/custos/.arx" \
  custos-runner:v0.3.0 vault put \
  --key-id binance-testnet \
  --tenant-id "$CUSTOS_TENANT_ID" \
  --api-key '<binance-testnet-api-key>' \
  --api-secret-stdin \
  --age-recipient "$SOPS_AGE_RECIPIENT" \
  --permission-scope trade_no_withdraw
```

## 3. Validate and run

```bash
docker run --rm \
  -v "$PWD/spec-example.json:/spec.json:ro" \
  custos-runner:v0.3.0 deployment validate --spec-file /spec.json

docker compose up
```

The local JSON file is an offline execution-view fixture. Create, approve,
promote, stop, or archive the real deployment through Crucible. Custos consumes
the signed command and emits signed lifecycle facts; it never becomes the
business fact owner. Observe only the runner with `docker compose logs -f runner`.

Remote release remains deferred; this workflow consumes no GHCR artifact.
