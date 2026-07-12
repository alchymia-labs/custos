# SuperTrend on Binance testnet with custos 0.3.0

This Compose example uses the complete official Custos image directly. It starts
JetStream, creates the standalone stream topology once, waits for runner
readiness, and publishes the included DeploymentSpec through the public CLI.
No derived Custos Dockerfile is required.

Exchange credentials, the age private key, and strategy code remain under this
directory on the operator host. Testnet credentials must allow trading but not
withdrawal.

## Prerequisites

- Docker with Compose v2.
- `uv` with this repository synced (`uv sync --extra dev`) for the sanctioned
  local `runner.toml` helper.
- A reviewed strategy at `strategy/strategy.py`.
- `age-keygen` for the one-time local key creation.
- Binance Futures testnet credentials with withdrawal disabled.

Copy the non-secret defaults without overwriting an existing configuration:

```bash
test -f .env || cp .env.example .env
set -a
. ./.env
set +a
```

## 1. Provision the local identity and per-key vault

Create the runtime directories and age identity locally:

```bash
mkdir -p runtime/.arx/vault runtime/.arx/state
chmod 700 runtime/.arx runtime/.arx/vault runtime/.arx/state
age-keygen -o runtime/.arx/age.key
chmod 600 runtime/.arx/age.key
```

Use the official image's `arx-runner vault put` command to write the encrypted
credential. Pass the secret through stdin:

```bash
printf '%s\n' '<binance-testnet-api-secret>' | docker run --rm -i \
  -v "$PWD/runtime/.arx:/home/custos/.arx" \
  ghcr.io/the-alephain-guild/custos:v0.3.0 vault put \
  --key-id binance-testnet \
  --tenant-id "$ARX_TENANT_ID" \
  --api-key '<binance-testnet-api-key>' \
  --api-secret-stdin \
  --age-recipient '<age1-public-key>' \
  --permission-scope trade_no_withdraw
```

Create the sanctioned non-live `runner.toml` with the repository checkout:

```bash
uv run python - <<'PY'
import os
import time
from pathlib import Path

from custos.core.runner_toml import RunnerToml

RunnerToml.write(
    Path("runtime/.arx/runner.toml"),
    RunnerToml(
        tenant_id=os.environ["ARX_TENANT_ID"],
        runner_id=os.environ["ARX_RUNNER_ID"],
        backend_url="http://standalone.invalid",
        long_term_credential="testnet-local-only",
        enrolled_at_ns=time.time_ns(),
    ),
)
PY
```

Production runners must use `arx-runner enroll`; this manual record is only the
documented sandbox/testnet path.

## 2. Start, wait, and publish

```bash
docker compose up
```

The service order is explicit:

1. `nats` starts JetStream.
2. `nats-bootstrap` idempotently creates Custos-owned streams.
3. `runner` starts with `--engine nautilus` and becomes healthy only after its
   DeploymentSpec subscription is established.
4. `spec-publisher` runs `arx-runner deployment publish` and exits after the
   JetStream acknowledgement.

Observe the reconcile result with:

```bash
docker compose logs -f runner spec-publisher
```

To stop the deployment, set `generation` to `2` and `lifecycle_state` to
`stopped` in `spec-example.json`, then publish the new desired state:

```bash
docker compose run --rm spec-publisher
```

The official image defaults to the real Nautilus engine. This example passes it
explicitly so the runtime intent remains visible in Compose.
