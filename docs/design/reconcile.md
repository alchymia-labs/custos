# Deployment reconciliation

## Input contract

The runner command coordinator consumes a Crucible-signed domain event on:

    crucible_rust.domain.<tenant>.<mode>.deployment.
      DeploymentSpecReadyForRunner.<runner_id>.<deployment_instance_id>

The verifier authenticates the exact NATS subject and exact serialized event
bytes before the JSON payload is trusted. The payload carries the immutable
DeploymentSpec, exact deployment instance, desired lifecycle state and
generation.

## State model

The v1.team reconciliation authority is durable in the existing RunnerFact SQLite
deep module:

    desired_deployments[deployment_instance_id]
    applied_deployments[deployment_instance_id]
    command_in_progress_lease[deployment_instance_id]
    command_outcomes[outcome_id]
    runner_fact_outbox[batch_id]

deployment_spec_id is never used as the map key. This permits multiple
instances of one immutable spec and prevents a retry from controlling the
wrong process.

There is no in-memory reconciler, spec-keyed watermark or compatibility
fallback. A command which cannot enter the RunnerFact authority is rejected
fail closed; runtime code never reconstructs authority from a local path or an
older payload shape.

## Reconciliation algorithm

1. Verify the signed envelope and exact subject binding before parsing payload fields.
2. Validate tenant, mode, runner, instance, spec digest, release binding and generation.
3. Persist the exact command and compare it with the accepted generation for that instance.
4. On `PREPARED_FOR_APPLY` or `IDEMPOTENT_PENDING`, load the exact durable desired record.
5. Resolve Crucible-owned StrategyRelease material through the authenticated V1 resolver.
6. Verify and activate the exact artifact under the immutable activation root. An exact
   redelivery reloads the durable activation; it never imports a mutable source path.
7. Resolve the signed credential scope locally and apply through
   `EngineLifecycleSupervisor`, passing the verified activated artifact as a required ABI input.
8. Wait for the typed seven-check `EngineReadyReceipt`; task creation alone is insufficient.
9. Atomically commit applied state and the deterministic lifecycle fact in the T4 transaction.
10. ACK only after that transaction. A matching restart/redelivery probes ready state and does
    not repeat deployment.

The lifecycle event ID is derived from stream authority, spec id/digest,
generation, lifecycle state, stable command fingerprint and outcome; observation
time remains payload only. No timestamp, local file or reconstructed payload can
replace the signed command fingerprint.

## Delivery disposition

| Outcome | NATS disposition |
| --- | --- |
| bad signature, subject mismatch or invalid contract | durable untrusted rejection, then TERM |
| same generation and exact bytes | replay the prior durable disposition |
| same generation with different bytes, stale, retry exhausted | atomic terminal outcome/fact, then TERM |
| successful command application | atomic applied state/fact, then ACK |
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

Ready timeout, retryable terminal events and zombie disconnect share one durable
bounded restart budget with exponential backoff. A non-retryable terminal event
or exhausted budget atomically quarantines and enqueues the terminal lifecycle.
The daemon treats any unexpected long-running task exit as fatal, cancels sibling
tasks, then stops deployments, flushes the RunnerFact outbox and closes transports.

The fallback breaker reads exactly one `EngineStatus` per instance per tick.
That status is derived by the canonical Nautilus portfolio snapshot provider, so
open notional and actual portfolio equity have one valuation boundary. A probe
exception or typed unreliable status immediately freezes the breaker and requests
flattening; missing mark or equity can never skip a tick or be treated as zero
risk. This T6 safety behavior is local execution evidence only. It does not replace
the Crucible-signed versioned runner policy required by T7, and DeploymentSpec
execution configuration cannot define or override the runner aggregate cap.
