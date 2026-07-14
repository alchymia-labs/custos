# RunnerFact production

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

Every deployment-scoped fact carries tenant, mode, runner,
deployment_instance_id, deployment_spec_id, deployment_spec_digest, event time,
event id and typed payload. Strategy, spec or process identifiers cannot replace
deployment_instance_id as the runtime identity.

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
