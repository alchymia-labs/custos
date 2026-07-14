# Deployment reconciliation

## Input contract

The reconciler consumes a Crucible-signed domain event on:

    crucible_rust.domain.<tenant>.<mode>.deployment.
      DeploymentSpecReadyForRunner.<runner_id>.<deployment_instance_id>

The verifier authenticates the exact NATS subject and exact serialized event
bytes before the JSON payload is trusted. The payload carries the immutable
DeploymentSpec, exact deployment instance, desired lifecycle state and
generation.

## State model

The in-memory reconciliation map is:

    deployment_instance_id -> {
      applied_generation,
      reported_generation,
      deployment_spec_id,
      deployment_spec_digest,
      desired_state,
      engine_handle,
      last_observation
    }

deployment_spec_id is never used as the map key. This permits multiple
instances of one immutable spec and prevents a retry from controlling the
wrong process.

## Reconciliation algorithm

1. Verify the signed envelope and subject binding.
2. Validate tenant, mode, runner, instance, spec digest and live evidence.
3. Compare generation with the accepted generation for that instance.
4. Translate the canonical spec into the narrow local engine configuration.
5. Apply start, reconfigure or stop to the engine using the instance id.
6. Advance applied_generation only after the engine operation succeeds.
7. Durably enqueue RunnerDeploymentLifecycleFact.v1 and then advance reported_generation.
8. ACK only after both watermarks reach the desired generation; redelivery after
   an emit failure retries the fact without repeating the engine operation.

## Delivery disposition

| Outcome | NATS disposition |
| --- | --- |
| bad signature, subject mismatch or invalid contract | ACK and emit security or audit observation |
| stale or duplicate generation | ACK as idempotent no-op |
| successful reconciliation | ACK |
| transient engine or local dependency failure | NAK for redelivery |

A poison command must not create an infinite redelivery loop. A transient
execution failure must not be acknowledged as success.

## Supervision

Zombie detection, circuit-breaker state, peak-equity tracking and engine task
completion are keyed by deployment_instance_id. Credential secrets remain
indexed by the signed credential scope id, while each use is bound to the
deployment instance. Their facts
retain deployment_spec_id only to explain which immutable configuration was
executed.
