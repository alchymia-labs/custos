# Custos mandatory rules

## Ownership

- ARX authenticates actors and authorizes intent.
- Crucible owns all business workflows, DeploymentSpecs,
  DeploymentInstances and canonical facts.
- Custos owns local execution, safety and signed runner observations only.
- Custos must not publish or relay canonical business state through ARX.

## Runtime identity

- deployment_instance_id is the primary key for reconciler, engine, watchdog,
  breaker, credential and telemetry state.
- deployment_spec_id is immutable configuration provenance only.
- tenant and mode must be explicit and must agree across subject, envelope and
  payload.

## Trust

- Accept deployment desired state only after Crucible exact-byte and
  exact-subject signature verification.
- Live mode fails closed without signed promotion evidence.
- RunnerFacts use enrolled runner signing keys and address one exact deployment
  instance.
- No unsigned compatibility or network-trust fallback is permitted.

## Safety

- Local stop and flatten remain available during upstream outage.
- Invalid commands are terminally rejected and audited.
- Transient engine or delivery failures remain retryable.
- No safety or audit failure may be silently swallowed.

## Repository authority

authority-manifest.json and scripts/check-authority-docs.py define the local
authority gate. Update them together with any migration, ownership or protocol
change.
