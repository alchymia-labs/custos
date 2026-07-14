# Custos operations runbook

Custos consumes signed Crucible commands and emits signed RunnerFacts. It does
not own deployment business state, approval workflow, business NATS topology,
or unsigned telemetry publication.

## Logging rules

- Logs are structured JSON.
- Never log API secrets, opaque machine credentials, private keys, enrollment
  tokens, or decrypted vault values.
- Runtime events use `deployment_instance_id`; `spec_id` is provenance only.

## Startup authority failure

Symptoms: `Runner startup authority check failed` and no ready file.

Check:

1. `runner.toml` exists with mode `0600` and contains only public metadata.
2. Its `machine_vault_path` points at the enrolled machine vault.
3. `SOPS_AGE_KEY_FILE` exists with mode `0600` and decrypts that vault.
4. Credential ID, version, expiry, tenant, runner, and machine key match the
   metadata exactly.

Do not hand-edit authority files. Revoke or rotate through Crucible, or enroll
a new machine principal with a new one-time token.

## Venue vault failure

Symptoms: credential decrypt or permission-scope failure before engine deploy.

```bash
arx-runner vault verify --key-id binance-testnet --tenant-id acme
```

Each venue credential must be a separate sops+age document with
`trade_no_withdraw` scope. Replace a bad entry with `arx-runner vault put`; do
not place secrets in argv, runner.toml, or DeploymentSpec.

## Deployment command rejection

Common causes:

- invalid Crucible signature or key ID;
- subject tenant/runner/instance does not match the signed payload;
- canonical DeploymentSpec digest mismatch;
- stale generation or changed strategy identity for an existing instance;
- strategy `code_hash` mismatch;
- live command missing Crucible promotion evidence;
- live command routed to a non-live engine host.

Use offline validation only as a local diagnostic:

```bash
arx-runner deployment validate \
  --spec-file deployment.json \
  --strategy-dir /opt/custos/strategies/supertrend
```

Correct canonical state in Crucible and let it emit a new signed generation.
Never inject a command directly into NATS.

## NATS or Crucible outage

Readiness clears when the exact runner subscription is unavailable. Custos
continues local safety enforcement and retries subscription with bounded
backoff. It does not silently switch to ARX or an unsigned topic.

Applied observations remain in the signed RunnerFact outbox. Once connectivity
returns, the outbox publisher resumes without changing fact identity or
sequence ownership.

Useful checks:

```bash
arx-runner health
du -h ~/.arx/state/runner-fact-outbox.db
```

## Engine or venue failure

For authentication failures, verify exchange key status, IP allowlists, clock
synchronization, and `trade_no_withdraw` scope. For code-hash failures, deploy
the reviewed strategy bytes matching the Crucible spec. Never bypass the G6
live capability gate.

Fallback breakers, the local notional cap, and the zombie watchdog are keyed by
`deployment_instance_id`. A trip for one instance must not flatten or stop a
different instance.

## Process recovery

1. Inspect `journalctl -u custos -n 200` or container logs.
2. Preserve `.arx/runner.toml`, the machine vault, venue vault, Crucible public
   key, and RunnerFact outbox.
3. Restart the service.
4. Confirm `arx-runner health` succeeds.
5. Confirm Crucible receives the expected lifecycle fact generation.

The runner resumes from enrolled machine authority and Crucible desired state.
No long-term credential is stored in runner.toml, and no local file is the
canonical deployment lifecycle record.

## Canonical events

| Event | Meaning |
|---|---|
| `deployment_reconciler_subscribe_failed` | Crucible command subscription unavailable |
| `deployment_spec_decode_failed` | Signed event or subject failed verification/parsing |
| `deployment_reconcile_failed` | Local engine apply failed for an instance |
| `deployment_lifecycle_fact_enqueue_failed` | Applied generation was not durably reported |
| `g6_gate_live_capability_denied` | Host cannot execute live safely |
| `nt_stop_noop_unknown_instance` | Idempotent stop for an absent instance |

See [`05-deployment.md`](05-deployment.md) for provisioning and startup.
