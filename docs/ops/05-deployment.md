# 05 — Custos 0.3.0 deployment

Custos is a self-hosted daemon. Arx publishes declarative desired state; it
does not enter the operator's machine or start containers there. Venue keys,
the age identity, and strategy code stay on the runner host.

## Supported runtime

The current downstream-development artifact is the complete, verified local
image:

```text
custos-runner:v0.3.0
```

**Remote release: deferred.** The GitHub/PyPI/GHCR publication and signing
identity are not established by the current repository state.

It contains Python 3.12, NautilusTrader, PyYAML, sops, age, and the
`arx-runner` CLI. The image runs as UID/GID 1000, declares
`/home/custos/.arx` as its persistent volume, uses `arx-runner` as the
entrypoint, defaults to `start`, and probes readiness with `arx-runner health`.

Downstream deployment projects consume this image directly. They must not add
a derived Custos Dockerfile merely to install runtime dependencies. Their
owned input is strategy code plus the opaque `strategy_config`; Custos owns
spec validation, Vault, NATS topology, transport, and engine wiring.

## Prerequisites

- Docker with Compose v2 for the recommended path.
- A JetStream-enabled NATS endpoint reachable from the runner.
- A nonce-bound Runner machine identity created only by `arx-runner enroll`.
  Manual `runner.toml` records are not supported in any mode.
- An age identity at `~/.arx/age.key`, mode `0600`.
- One sops-encrypted file per credential under `~/.arx/vault/`, each limited
  to `trade_no_withdraw`.
- For live mode, a matching strategy-directory `code_hash`, a supported venue,
  a live-capable host, and at least two distinct cloud approvers.

## Recommended standalone Compose path

The runnable
[`examples/supertrend-testnet`](../../examples/supertrend-testnet/) stack is
the golden path:

```bash
make verify-local-v030
cd examples/supertrend-testnet
test -f .env || cp .env.example .env
docker compose up
```

Its service order is explicit:

1. Start NATS with JetStream.
2. Run `arx-runner nats bootstrap --profile standalone` once. Bootstrap is
   idempotent and owns only deterministic Custos streams.
3. Start the runner with `--engine nautilus` and a persistent `.arx` mount.
4. Wait for `arx-runner health` to confirm the deployment subscription.
5. Publish a validated spec with `arx-runner deployment publish` and wait for
   its JetStream acknowledgement.

`arx-runner start` never creates streams implicitly. Managed installations
have the coordination plane provision topology; standalone installations run
the explicit bootstrap command.

## Identity and Vault provisioning

Generate the age identity first. Enrollment then writes an encrypted machine
principal plus non-secret `runner.toml` metadata:

```bash
mkdir -p "$HOME/.arx/vault" "$HOME/.arx/state"
chmod 700 "$HOME/.arx" "$HOME/.arx/vault" "$HOME/.arx/state"
age-keygen -o "$HOME/.arx/age.key"
chmod 600 "$HOME/.arx/age.key"

export SOPS_AGE_RECIPIENT='<age1-public-key>'
export SOPS_AGE_KEY_FILE="$HOME/.arx/age.key"

arx-runner enroll \
  --token '<one-time-enrollment-token>' \
  --backend https://arx.internal:8000 \
  --tenant-id acme \
  --runner-id 018f8b5f-6f7d-7e23-8c31-bd34ab9d0d41

arx-runner credential verify
arx-runner onboard --manifest runner-capability.json

printf '%s\n' '<venue-api-secret>' | arx-runner vault put \
  --key-id binance-testnet \
  --tenant-id acme \
  --api-key '<venue-api-key>' \
  --api-secret-stdin \
  --permission-scope trade_no_withdraw

arx-runner vault verify --key-id binance-testnet --tenant-id acme
```

Plaintext secrets enter through stdin, never argv or the deployment spec.

## Docker runtime volume and command

Build, gate, and inspect the local runtime:

```bash
make verify-local-v030
docker run --rm custos-runner:v0.3.0 --help
```

The runner reads identity and credentials from the bind-mounted `.arx`
directory. On Linux, mapping the process to the operator UID/GID keeps host
files accessible while preserving the image's non-root execution model:

```bash
docker run --rm --name custos \
  --user "$(id -u):$(id -g)" \
  -v "$HOME/.arx:/home/custos/.arx" \
  -v "$PWD/strategy:/opt/custos/strategies/supertrend:ro" \
  -e SOPS_AGE_KEY_FILE=/home/custos/.arx/age.key \
  custos-runner:v0.3.0 \
  start \
  --nats-url nats://arx.internal:4222 \
  --reconcile-strategy-id supertrend-btcusdt \
  --engine nautilus
```

Do not omit the persistent mount: an anonymous or ephemeral `.arx` loses the
runner record and encrypted Vault at container replacement. The mount must be
readable and writable by the selected non-root UID. OCI provenance labels can
be inspected with:

```bash
docker inspect --format \
  '{{index .Config.Labels "org.opencontainers.image.revision"}}' \
  custos-runner:v0.3.0
```

Future remote release signature verification is implemented by
[`verify-release.sh`](../../.github/workflows/scripts/verify-release.sh), but
it is not evidence that a 0.3.0 registry artifact has already been published.

## Source and systemd path

Source development is separate from the release-image path:

```bash
make install-nt
uv run arx-runner --help
```

The equivalent long-running unit is:

```ini
[Unit]
Description=Custos self-hosted trading runner
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=custos
Group=custos
WorkingDirectory=/opt/custos
Environment="SOPS_AGE_KEY_FILE=/home/custos/.arx/age.key"
ExecStart=/opt/custos/.venv/bin/arx-runner start --nats-url nats://arx.internal:4222 --reconcile-strategy-id supertrend-btcusdt --engine nautilus
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

`tenant_id`, `runner_id`, credential ID/version/expiry, key ID, and the
encrypted-vault reference come from `runner.toml`; the opaque credential and
private key are decrypted only in memory from `runner-machine.enc`.

## DeploymentSpec publication

Validate locally before publishing. Live specs pass the strategy directory to
both commands so validation and publication compute the same canonical hash:

```bash
arx-runner deployment validate \
  --spec-file deployment.json \
  --strategy-dir /opt/custos/strategies/supertrend
arx-runner deployment publish \
  --spec-file deployment.json \
  --strategy-dir /opt/custos/strategies/supertrend \
  --tenant-id acme \
  --strategy-id supertrend-btcusdt \
  --nats-url nats://arx.internal:4222
```

For non-live specs, `--strategy-dir` may be omitted. Do not import an
engine-private hash module.

The lifecycle sequence is generation-driven. Increment `generation` for every
desired-state change. `stopped` and `archived` reconcile to
`DeploymentStatus.phase=stopped`; `paused` preserves the deployment without
misclassifying it as a trading mode.

## Readiness and troubleshooting

```bash
arx-runner health
```

Exit 0 means machine authority is active and the deployment subscription is
established. Missing, expired, revoked, binding-mismatched, stale, or invalid
authority exits non-zero before the execution loop starts. Subscription failures clear readiness and
retry with bounded exponential backoff while local safety guards continue to
tick.

For common failures, see [`runbook.md`](runbook.md). Useful first checks are:

```bash
arx-runner vault verify --key-id binance-testnet --tenant-id acme
arx-runner deployment validate --spec-file deployment.json
docker compose logs -f runner nats-bootstrap spec-publisher
```

## Upgrade notes

0.3.0 is a clean break. Engine selection is `--engine nautilus|noop`; the
former is the default and the latter is only a non-live contract-test stub.
No compatibility alias exists. Operators upgrading from 0.1.x must first
complete the 0.2.0 namespace and per-key Vault migration documented in
[`CHANGELOG.md`](../../CHANGELOG.md).

The downstream gate is mandatory:

```text
PS Plan 49 must not execute against custos < 0.3.0.
PS must consume the verified local image directly.
PS must not maintain a derived custos Dockerfile.
PS owns strategy_config assembly only.
```
