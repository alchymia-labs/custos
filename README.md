# Custos

Custos is the local execution boundary for the Alephain trading platform. It
runs a strategy deployment on an enrolled runner, protects the local process,
and reports signed execution facts. It is not a business workflow service and
it is not an authorization gateway.

## Production topology

    human or API client
      -> ARX: authenticate actor and authorize intent
      -> Crucible: validate business rules, persist state, approve and sign command
      -> Custos: verify command, reconcile local runtime, sign execution facts
      -> Crucible: persist facts and advance canonical lifecycle

ARX may consume audit or read-model events, but it is never a relay for a
DeploymentSpec or a RunnerFact.

## Runtime identity

deployment_instance_id is the only key for a running deployment. A
deployment_spec_id identifies immutable configuration provenance and may be
shared by multiple instances. Reconciler state, engine handles, watchdogs,
circuit breakers and deployment-scoped facts are therefore instance keyed.
Secret material is looked up by its signed credential scope identifier; every
use is bound and audited against the exact deployment instance.

## Trust boundary

Custos accepts deployment commands only from the Crucible signed domain-event
stream. It verifies the exact NATS subject and exact event bytes with the
configured Ed25519 public key before parsing the command. Live execution also
requires the signed promotion identifier and evidence digest carried by the
canonical DeploymentSpec. Custos does not count human approvals or recreate a
business approval workflow.

Runner facts are signed locally and include tenant, mode, runner and exact
deployment instance identity. Crucible is the canonical consumer and owner of
those facts.

## Local use

    uv sync
    uv run arx-runner --help
    uv run arx-runner start --help

The authoritative document manifest is authority-manifest.json. Run
make check-authority to check referenced documents, migration heads and
forbidden topology drift.
