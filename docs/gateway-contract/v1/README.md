# Gateway Contract v1

The normative JSON Schemas in this directory freeze the wire shape of the
Custos deployment consumer contract and the four CustosGateway payloads that
flow between the `custos-runner` daemon and the arx-side coordination service:

| Schema | Payload |
| ------ | ------- |
| [`enrollment.schema.json`](enrollment.schema.json) | `validate_enrollment` request body — one-shot pairing at daemon startup |
| [`deployment_status.schema.json`](deployment_status.schema.json) | `record_deployment_status` observation body — reconciler heartbeat of what the runner actually has running |
| [`telemetry_snapshot.schema.json`](telemetry_snapshot.schema.json) | `ingest_telemetry` snapshot body — engine-status telemetry from the telemetry actor |
| [`heartbeat.schema.json`](heartbeat.schema.json) | `handle_heartbeat` payload — at-most-once liveness ping |

[`samples/`](samples/) contains one normative example for each of these four schemas.
CI validates every sample, including the deployment spec below, against its
corresponding Draft 2020-12 schema.

## DeploymentSpec consumer contract

[`deployment_spec.schema.json`](deployment_spec.schema.json) and
[`samples/deployment_spec_sandbox.json`](samples/deployment_spec_sandbox.json) describe
the normative DeploymentSpec shape accepted by the Custos runtime. The schema is generated
from `custos.contracts.DeploymentSpec`, and CI requires the checked-in JSON to remain exactly
equal to `DeploymentSpec.model_json_schema()`. Unknown top-level properties are rejected.
`generation` starts at 1, lifecycle is one of `running`, `paused`, `stopped`, or `archived`,
sandbox mode requires starting balances, and live mode requires a lowercase 64-character
SHA-256 `code_hash`.

## Additive-only rule

**Adding an optional field is a coordinated MINOR bump.** The producer and
consumer must land the same minor before the producer emits it. Because the
consumer uses `additionalProperties: false`, an older runner rejects a field
it does not know instead of silently accepting a misspelling or unsupported
extension.

**Adding a new required field is a MAJOR bump.** An old runner would not
emit the field; validation would fail.

**Removing a property is a MAJOR bump.** An old consumer might still
read it.

**Renaming a property is TWO MAJOR bumps** — first deprecate + accept
both, then remove. Never rename in place.

The
[`tests/test_gateway_contract_v1_backward_compat.py`](../../../tests/test_gateway_contract_v1_backward_compat.py)
suite enforces both invariants against a golden snapshot at
[`tests/fixtures/gateway_contract_v1_golden/`](../../../tests/fixtures/gateway_contract_v1_golden/).

## v2 protocol

When a breaking change is unavoidable, cut a new directory
`docs/gateway-contract/v2/` with a fresh set of schemas + goldens. The
v1 directory stays frozen for the duration of every LTS line that
depends on it. The
[`../lts-commitment.md`](../lts-commitment.md) EOL window pins the
minimum period v1 stays queryable.

## Sourced from

The payloads mirror the arx-side Rust trait
`CustosGateway`, defined at
`arx/backend/crates/coordination/src/custos.rs:9-30`. Every schema field
here corresponds to an argument (or an observed field) of one of the
four `async fn` methods:

- `validate_enrollment(&self, token: &str)` → `enrollment.schema.json`
- `record_deployment_status(&self, tenant: &TenantId, spec_id: &str,
  status: &str)` → `deployment_status.schema.json`
- `ingest_telemetry(&self, tenant: &TenantId, snapshot_json: &str)` →
  `telemetry_snapshot.schema.json` (the `snapshot_json` argument is
  wrapped in the NATS envelope; the schema here covers the inner
  payload)
- `handle_heartbeat(&self, tenant: &TenantId, runner_id: &str)` →
  `heartbeat.schema.json`

`tenant_id` is intentionally NOT part of the payload — arx resolves it
server-side from the OIDC / token boundary, so putting it in the wire
body would create a source-of-truth conflict.
