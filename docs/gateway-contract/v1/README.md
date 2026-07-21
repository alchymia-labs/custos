# Custos runner contract V1

This directory contains contracts owned and published by Custos. It does not
publish a DeploymentSpec schema. Crucible owns the canonical DeploymentSpec,
its exact-byte command schema, its golden and the producer receipt.

Custos consumes only the two signed, runner-scoped command events:

- `DeploymentSpecReadyForRunner.<runner_id>.<deployment_instance_id>`;
- `DeploymentInstanceDesiredStateChanged.<runner_id>.<deployment_instance_id>`.

`CrucibleRunnerDeploymentCommandV1` verifies the exact subject, signed event
bytes, canonical digest, tenant, runner, instance, spec and generation. The
canonical payload contains one typed `execution_config`; it contains no source
path, artifact path, `code_hash` or generic `parameters` fallback.

Strategy code material is resolved from authenticated Crucible
`StrategyRelease` authority, verified locally against the signed release,
snapshot, artifact and manifest digests, activated atomically, then passed to
the engine as an `ActivatedEngineArtifactV1`. The engine never imports a path
from a command.

Runner lifecycle observations use the signed RunnerFact V1 outbox. The outbox
allocates `facts[].seq`; typed fact builders never supply it.

`deployment_instance_id` is the sole runtime primary key. The spec ID, spec
digest and generation are immutable fencing/provenance fields and never create
a second stream.

Readiness is fail closed. Until the authenticated StrategyRelease resolver and
its exact producer receipt are composed, `arx-runner start --reconcile` refuses
to start rather than selecting a legacy or unsigned path.
