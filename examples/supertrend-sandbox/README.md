# SuperTrend sandbox with Custos 0.3.0

This example runs a NautilusTrader strategy with live market data and locally
simulated fills. Exchange credentials, the age key, and strategy code remain on
the runner host.

Install the development and NautilusTrader extras on Python 3.12+:

```bash
uv sync --extra dev --extra nautilus
```

[`spec-example.json`](spec-example.json) is byte-identical to the informative
[`deployment_spec_sandbox.json`](../../docs/gateway-contract/v1/samples/deployment_spec_sandbox.json)
gateway sample. Set its `strategy_path` to the strategy file on this host before
publishing it.

## 1. Provision one per-key vault entry

Generate an age key once, then pass the secret through stdin. The only accepted
permission boundary in Custos 0.3.x is `trade_no_withdraw`.

```bash
mkdir -p ~/.arx/vault
chmod 700 ~/.arx ~/.arx/vault
age-keygen -o ~/.arx/age.key
chmod 600 ~/.arx/age.key

printf '%s\n' '<sandbox-api-secret>' | uv run arx-runner vault put \
  --key-id binance-sandbox-key \
  --tenant-id acme \
  --api-key '<sandbox-api-key>' \
  --api-secret-stdin \
  --age-recipient '<age1-public-key>' \
  --permission-scope trade_no_withdraw
```

The command writes `~/.arx/vault/binance-sandbox-key.enc`; it never creates a
shared multi-credential file.

## 2. Create the sanctioned sandbox runner.toml

When no enrollment backend is available, a manually constructed runner record
is an approved non-live path. It does not grant live scope.

```bash
uv run python - <<'PY'
import time
from pathlib import Path

from custos.core.runner_toml import RunnerToml

RunnerToml.write(
    Path.home() / ".arx" / "runner.toml",
    RunnerToml(
        tenant_id="acme",
        runner_id="runner-sandbox-1",
        backend_url="http://mock-sandbox:8000",
        long_term_credential="sandbox-local-only",
        enrolled_at_ns=time.time_ns(),
    ),
)
PY
```

See the full security and mode constraints in
[`docs/design/enrollment.md`](../../docs/design/enrollment.md#sandbox-mode-manually-constructed-runnertoml-sanctioned-pattern).

## 3. Start and publish the spec

Start a local JetStream-enabled NATS server, bootstrap the standalone topology,
then run the real Nautilus engine:

```bash
export SOPS_AGE_KEY_FILE="$HOME/.arx/age.key"
uv run arx-runner nats bootstrap \
  --profile standalone \
  --nats-url nats://localhost:4222 \
  --tenant-id acme

uv run arx-runner start \
  --nats-url nats://localhost:4222 \
  --reconcile-strategy-id supertrend-btcusdt \
  --engine nautilus \
  --vault-dir "$HOME/.arx/vault"
```

In another terminal, publish the strict DeploymentSpec through the public seam:

```bash
uv run arx-runner deployment publish \
  --spec-file examples/supertrend-sandbox/spec-example.json \
  --tenant-id acme \
  --strategy-id supertrend-btcusdt \
  --nats-url nats://localhost:4222
```

A `null` `code_hash` is permitted for sandbox and audited as a skipped
provenance check; live mode requires a matching hash and the G6 gate.
