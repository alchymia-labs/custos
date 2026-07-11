# SuperTrend on Binance testnet with custos 0.2.0

This Compose example exercises the local reconcile → G6 gate →
`NtTradingNodeHost` → Binance testnet path. It uses test funds only. Exchange
credentials and the age private key stay under `runtime/.arx` on this host.

The example retains a dedicated Dockerfile because the official v0.2.0 image
does not yet bundle NautilusTrader, sops, or age.

## Prerequisites

- Docker with Compose v2.
- A reviewed NautilusTrader strategy at `strategy/strategy.py`.
- Binance Futures testnet API credentials restricted to trading with no
  withdrawal permission.
- `uv`, `sops`, and `age` on the provisioning host.

Copy the non-secret configuration and load it into the current shell:

```bash
cp .env.example .env
set -a
. ./.env
set +a
```

## 1. Provision one per-key vault entry

`arx-runner vault put` writes one encrypted file for `binance-testnet`. The
fixture at `vault-fixture/credentials.example.json` documents the decrypted
single-key shape but is not written to disk during provisioning.

```bash
mkdir -p runtime/.arx/vault
chmod 700 runtime/.arx runtime/.arx/vault
age-keygen -o runtime/.arx/age.key
chmod 600 runtime/.arx/age.key

printf '%s\n' '<binance-testnet-api-secret>' | uv run arx-runner vault put \
  --key-id binance-testnet \
  --tenant-id "$ARX_TENANT_ID" \
  --api-key '<binance-testnet-api-key>' \
  --api-secret-stdin \
  --age-recipient '<age1-public-key>' \
  --permission-scope trade_no_withdraw \
  --vault-dir runtime/.arx/vault
```

The CLI and decrypt path both reject any scope other than
`trade_no_withdraw`.

## 2. Create the sanctioned testnet runner.toml

Without a real enrollment backend, build the documented non-live runner record:

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
        backend_url="http://mock-testnet:8000",
        long_term_credential="testnet-local-only",
        enrolled_at_ns=time.time_ns(),
    ),
)
PY
```

This sanctioned path never grants live scope. Production runners must use
`arx-runner enroll`.

## 3. Start the stack

```bash
docker compose up --build
```

The image entrypoint is `arx-runner`; Compose supplies the `start` subcommand,
NATS endpoint, strategy id, NautilusTrader host selection, and per-key vault
directory. The bind mount maps `runtime/.arx` to `/root/.arx`, so both
`runner.toml` and `vault/binance-testnet.enc` are available inside the runner.

## Publish and observe

Normally arx publishes [`spec-example.json`](spec-example.json). For a local
smoke test, publish it as the payload on
`arx.<tenant>.deployment_spec.<strategy_id>` and watch:

```bash
docker compose logs -f runner
```

Expect `nt_deploy_started` with `trading_mode=testnet`. Increase `generation`
and set `lifecycle_state` to `stopped` to stop the deployment. Testnet permits
`code_hash: null`; live mode requires a matching strategy-directory hash and
must pass every G6 gate layer.
