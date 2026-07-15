# RunnerFact v1 production authority

## Ownership

Custos observes the local engine. Crucible owns canonical business and lifecycle
facts. ARX may consume audit projections but is not in the publication path.

    engine / watchdog / breaker
      -> typed local fact adapter
      -> RunnerFactOutbox
      -> signed RunnerFact batch
      -> Crucible ingestion and projection

There is no generic unsigned NATS telemetry actor. Engine observations must map
to an explicitly versioned fact type before entering the durable outbox.

## Required identity

Every deployment-scoped signed batch carries tenant, mode, runner,
deployment_instance_id, deployment_spec_id, deployment_spec_digest, generation,
strategy/capability provenance, event time, event id and typed payload. Strategy,
spec, generation or process identifiers cannot replace deployment_instance_id as
the runtime identity.

The subject and durable stream identity are stable across spec and generation
changes:

```text
crucible.runner_fact.{mode}.{tenant_id}.{runner_id}.{deployment_instance_id}
tenant_id + mode + runner_id + deployment_instance_id
```

`deployment_spec_id`, `deployment_spec_digest`, and `generation` are signed batch
fences. They never split the stream and never reset its source sequence. The v1
signing domain is `CRUCIBLE-RUNNER-FACT-BATCH-V1\0`.

## Closed fact union

The immutable v1 candidate retains the existing 13 wire kind names. Unknown
kinds are terminal contract violations; they cannot fall back to unsigned logs.

| Projector | Accepted `facts[].kind` |
|---|---|
| settlement | `execution_fill`, `fill`, `position_closed`, `fee`, `period_closed` |
| risk | `equity_snapshot`, `position_snapshot` |
| health | `heartbeat`, `RunnerRuntimeLogFact.v1` |
| reconciliation | `venue_ledger_snapshot_manifest`, `venue_ledger_snapshot_chunk`, `reconciliation_period_closed` |
| deployment lifecycle | `RunnerDeploymentLifecycleFact.v1` |

Payload numbers are either JSON integers or canonical decimal strings. Python
binary floats are rejected recursively before SQLite persistence so signatures
do not depend on language-specific number rendering.

`RunnerDeploymentLifecycleFact.v1` records an applied desired generation with:

- tenant_id and mode;
- runner_id;
- deployment_instance_id;
- deployment_spec_id and deployment_spec_digest;
- generation and lifecycle_state;
- observed_at;
- seq, allocated exclusively by RunnerFactOutbox when the fact enters the
  signed batch `facts[]` array.

Emission requires an exact `deployment_lifecycle` capability projector binding
for the same mode, instance, spec digest and strategy. A health-only authority
cannot emit lifecycle facts.

Typed fact builders must not pre-populate seq. RunnerFactOutbox rejects such an
input and assigns the stream-monotonic sequence in the same transaction that
persists the signed batch.

## Failure semantics

Outbox enqueue success is the reporting durability boundary. Reconciliation
keeps separate applied_generation and reported_generation watermarks. If enqueue
fails, Custos NAKs the command; redelivery retries only the fact and does not
repeat the successful engine action.

Local safety continues while Crucible is unavailable. Custos never downgrades a
fact to an unsigned compatibility topic.

## Candidate readiness ceiling

`custos.runner-fact.v1/candidate-2026-07-15.1` is a producer contract candidate.
Its synthetic Ed25519 key and signature are cross-language golden evidence only;
they are not runtime identity evidence. Until Crucible Plan 90 Phase A returns a
receipt over the exact candidate bytes, projector compatibility, runtime RC,
real round-trip, live, runtime and production readiness remain false.
